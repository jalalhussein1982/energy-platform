"""Minimal S3 client: SigV4 over ``httpx``, inside the single egress package (ADR-032 Option B).

Five verbs — ``PUT``, ``GET``, ``HEAD``, ``LIST`` (ListObjectsV2, paginated) and ``DELETE`` —
with path-style addressing, ``x-amz-content-sha256`` always set to the payload hash, object-lock
retention headers on ``PUT`` when configured (V-6), and the endpoint host checked against a
configured allowlist before any request (P2-D16). ``DELETE`` is refused unless the store was built
with ``allow_delete=True``; only the tiering job (ADR-021) sets it. Credentials come from the
environment through the ``secretRef`` resolver (P2-D17), never from a manifest.

The signer is a pure function (:func:`sign_v4`) so that it can be proven against the AWS
documentation vector without a network; the client never sends an unsigned request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import random
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from lxml import etree

from energy_platform.contracts.manifest import SecretRef
from energy_platform.fetch.client import DEFAULT_RETRY, RetryPolicy
from energy_platform.fetch.secrets import EnvSecretResolver, SecretMissing

log = logging.getLogger("energy_platform.fetch.objectstore")

ALGORITHM = "AWS4-HMAC-SHA256"
SERVICE = "s3"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_AMZ_DATE = "%Y%m%dT%H%M%SZ"
_RETAIN_UNTIL = "%Y-%m-%dT%H:%M:%SZ"
_UNRESERVED = "-_.~"
_XML_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True
)
_S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"

RetentionMode = Literal["COMPLIANCE", "GOVERNANCE"]


class ObjectStoreError(Exception):
    """The store refused or failed a request. ``code`` is stable for tests and logs."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# --------------------------------------------------------------------------- configuration


@dataclass(frozen=True, slots=True)
class Retention:
    """Object-lock retention applied to every ``PUT`` (ADR-002 immutability, V-6)."""

    mode: RetentionMode
    days: int

    def __post_init__(self) -> None:
        if self.days < 1:
            raise ValueError("retention days must be >= 1")


@dataclass(frozen=True, slots=True)
class ObjectStoreConfig:
    endpoint: str
    """``https://host[:port]`` (``http://`` needs ``allow_insecure``); path-style, no bucket."""
    bucket: str
    region: str = "us-east-1"
    allowed_hosts: tuple[str, ...] = ()
    """Exact, lowercase endpoint hosts this process may talk to (P2-D16)."""
    allow_insecure: bool = False
    allow_delete: bool = False
    """Only the tiering job sets this; a Bronze writer never deletes."""
    retention: Retention | None = None
    timeout: float = 30.0


@dataclass(frozen=True, slots=True)
class Credentials:
    access_key_id: str
    secret_access_key: str = field(repr=False)
    session_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, name: str, environ: dict[str, str] | None = None) -> Credentials:
        """``<NAME>_ACCESS_KEY_ID``, ``<NAME>_SECRET_ACCESS_KEY``, optional ``…_SESSION_TOKEN``."""
        resolver = EnvSecretResolver(environ)
        try:
            token: str | None = resolver.resolve(SecretRef(name=name, key="session-token"))
        except SecretMissing:
            token = None
        return cls(
            access_key_id=resolver.resolve(SecretRef(name=name, key="access-key-id")),
            secret_access_key=resolver.resolve(SecretRef(name=name, key="secret-access-key")),
            session_token=token,
        )


def check_endpoint(endpoint: str, allowed_hosts: tuple[str, ...], allow_insecure: bool) -> str:
    """Return the normalised ``scheme://netloc`` or raise before any connection is attempted."""
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if not host:
        raise ObjectStoreError("endpoint_not_allowed", f"{endpoint!r} has no host")
    if parts.scheme not in {"https", "http"}:
        raise ObjectStoreError("insecure_endpoint", f"{endpoint!r}: scheme must be https")
    if parts.scheme == "http" and not allow_insecure:
        raise ObjectStoreError("insecure_endpoint", f"{endpoint!r}: http needs allow_insecure")
    if parts.username is not None or parts.password is not None:
        raise ObjectStoreError("endpoint_not_allowed", f"{endpoint!r}: credentials in the URL")
    if parts.query or parts.fragment or parts.path not in {"", "/"}:
        raise ObjectStoreError("endpoint_not_allowed", f"{endpoint!r}: path, query or fragment")
    if host not in allowed_hosts:
        raise ObjectStoreError(
            "endpoint_not_allowed", f"{host!r} is not in the object-store allowlist {allowed_hosts}"
        )
    default = 443 if parts.scheme == "https" else 80
    netloc = host if parts.port in {None, default} else f"{host}:{parts.port}"
    return f"{parts.scheme}://{netloc}"


# --------------------------------------------------------------------------- signing


@dataclass(frozen=True, slots=True)
class SignedRequest:
    method: str
    url: str
    headers: dict[str, str]
    """Every header to send, including ``Authorization``; nothing else may be added or changed."""
    canonical_request: str
    string_to_sign: str
    signature: str


def _uri_encode(text: str, *, keep_slash: bool) -> str:
    return quote(text, safe=_UNRESERVED + ("/" if keep_slash else ""))


def _canonical_query(query: str) -> str:
    pairs: list[tuple[str, str]] = []
    for item in filter(None, query.split("&")):
        name, _, value = item.partition("=")
        pairs.append((name, value))
    return "&".join(f"{k}={v}" for k, v in sorted(pairs))


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def sign_v4(
    *,
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload_sha256: str,
    credentials: Credentials,
    region: str,
    at: datetime,
) -> SignedRequest:
    """AWS Signature Version 4 for one request; ``url`` is sent exactly as given.

    ``headers`` are signed in full (plus ``host``, ``x-amz-content-sha256``, ``x-amz-date`` and
    ``x-amz-security-token`` when a session token exists). The query string in ``url`` must
    already be URI-encoded; it is canonicalised by sorting only.
    """
    parts = urlsplit(url)
    stamp = at.astimezone(UTC).strftime(_AMZ_DATE)
    date = stamp[:8]
    all_headers = {k.lower().strip(): " ".join(v.split()) for k, v in headers.items()}
    all_headers["host"] = parts.netloc
    all_headers["x-amz-content-sha256"] = payload_sha256
    all_headers["x-amz-date"] = stamp
    if credentials.session_token:
        all_headers["x-amz-security-token"] = credentials.session_token
    names = sorted(all_headers)
    canonical_headers = "".join(f"{n}:{all_headers[n]}\n" for n in names)
    signed_headers = ";".join(names)
    canonical_request = "\n".join(
        [
            method.upper(),
            parts.path or "/",
            _canonical_query(parts.query),
            canonical_headers,
            signed_headers,
            payload_sha256,
        ]
    )
    scope = f"{date}/{region}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [ALGORITHM, stamp, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
    )
    key = _hmac(f"AWS4{credentials.secret_access_key}".encode(), date)
    for part in (region, SERVICE, "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    out = dict(all_headers)
    out["authorization"] = (
        f"{ALGORITHM} Credential={credentials.access_key_id}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return SignedRequest(
        method=method.upper(),
        url=url,
        headers=out,
        canonical_request=canonical_request,
        string_to_sign=string_to_sign,
        signature=signature,
    )


# --------------------------------------------------------------------------- client


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size: int
    etag: str | None
    content_type: str | None = None
    last_modified: str | None = None
    storage_class: str | None = None
    """From ``x-amz-storage-class``; gateways omit it for ``STANDARD`` (ADR-021 §3 probe)."""


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname


def _child_text(el: etree._Element, name: str) -> str | None:
    for child in el:
        if isinstance(child.tag, str) and _local(child) == name:
            return child.text
    return None


def _error_code(body: bytes) -> str:
    try:
        root = etree.fromstring(body, _XML_PARSER)
    except etree.XMLSyntaxError:
        return "unknown"
    if root is None:
        return "unknown"
    return _child_text(root, "Code") or "unknown"


class ObjectStore:
    """One bucket on one endpoint. Every request is signed; nothing is sent to another host."""

    def __init__(
        self,
        config: ObjectStoreConfig,
        credentials: Credentials,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        self._config = config
        self._base = check_endpoint(config.endpoint, config.allowed_hosts, config.allow_insecure)
        self._credentials = credentials
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.SystemRandom()
        self._retry = retry
        self._client: httpx.Client | None = None

    # ------------------------------------------------------------------ verbs

    @property
    def bucket(self) -> str:
        return self._config.bucket

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        storage_class: str | None = None,
    ) -> str:
        """Write one object and return its ETag; object-lock headers when retention is set;
        ``x-amz-storage-class`` only when asked (the ADR-021 §3 probe)."""
        headers = {
            "content-type": content_type,
            "content-md5": base64.b64encode(
                hashlib.md5(data, usedforsecurity=False).digest()  # S3's own integrity check
            ).decode(),
        }
        retention = self._config.retention
        if retention is not None:
            until = self._clock().astimezone(UTC) + timedelta(days=retention.days)
            headers["x-amz-object-lock-mode"] = retention.mode
            headers["x-amz-object-lock-retain-until-date"] = until.strftime(_RETAIN_UNTIL)
        if storage_class is not None:
            headers["x-amz-storage-class"] = storage_class
        response = self._request("PUT", self._object_url(key), headers=headers, body=data)
        self._raise_unless(response, {200}, key)
        return str(response.headers.get("etag", ""))

    def put_new(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> bool:
        """Create-only ``PUT`` (``If-None-Match: *``): ``False`` on 412 Precondition Failed,
        the object already existed (ADR-024 amendment 3). Object-lock headers as ``put``."""
        headers = {
            "content-type": content_type,
            "content-md5": base64.b64encode(
                hashlib.md5(data, usedforsecurity=False).digest()
            ).decode(),
            "if-none-match": "*",
        }
        retention = self._config.retention
        if retention is not None:
            until = self._clock().astimezone(UTC) + timedelta(days=retention.days)
            headers["x-amz-object-lock-mode"] = retention.mode
            headers["x-amz-object-lock-retain-until-date"] = until.strftime(_RETAIN_UNTIL)
        response = self._request("PUT", self._object_url(key), headers=headers, body=data)
        if response.status_code == 412:
            return False
        self._raise_unless(response, {200}, key)
        return True

    def get(self, key: str) -> bytes | None:
        """The object's bytes, or ``None`` when it does not exist (404)."""
        response = self._request("GET", self._object_url(key))
        if response.status_code == 404:
            return None
        self._raise_unless(response, {200}, key)
        return response.content

    def head(self, key: str) -> ObjectInfo | None:
        response = self._request("HEAD", self._object_url(key))
        if response.status_code == 404:
            return None
        self._raise_unless(response, {200}, key)
        return ObjectInfo(
            key=key,
            size=int(response.headers.get("content-length", "0")),
            etag=response.headers.get("etag"),
            content_type=response.headers.get("content-type"),
            last_modified=response.headers.get("last-modified"),
            storage_class=response.headers.get("x-amz-storage-class"),
        )

    def list(self, prefix: str, *, page_size: int = 1000) -> Iterator[ObjectInfo]:
        """ListObjectsV2 under ``prefix``; follows ``NextContinuationToken`` until exhausted."""
        token: str | None = None
        while True:
            params = {"list-type": "2", "max-keys": str(page_size), "prefix": prefix}
            if token is not None:
                params["continuation-token"] = token
            response = self._request("GET", self._bucket_url(params))
            self._raise_unless(response, {200}, prefix)
            page, token = _parse_listing(response.content)
            yield from page
            if token is None:
                return

    def delete(self, key: str) -> None:
        """Refused unless ``allow_delete``; the tiering job is the only legitimate caller."""
        if not self._config.allow_delete:
            raise ObjectStoreError(
                "delete_not_allowed", f"{key!r}: this store was not built with allow_delete"
            )
        response = self._request("DELETE", self._object_url(key))
        self._raise_unless(response, {200, 204}, key)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------ internals

    def _object_url(self, key: str) -> str:
        if not key or key.startswith("/"):
            raise ObjectStoreError("bad_key", f"{key!r}")
        bucket = _uri_encode(self.bucket, keep_slash=False)
        return f"{self._base}/{bucket}/{_uri_encode(key, keep_slash=True)}"

    def _bucket_url(self, params: Mapping[str, str]) -> str:
        query = "&".join(
            f"{_uri_encode(k, keep_slash=False)}={_uri_encode(v, keep_slash=False)}"
            for k, v in sorted(params.items())
        )
        return f"{self._base}/{_uri_encode(self.bucket, keep_slash=False)}?{query}"

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                transport=self._transport,
                follow_redirects=False,
                timeout=self._config.timeout,
                trust_env=True,
            )
        return self._client

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> httpx.Response:
        last_error: Exception = ObjectStoreError("request_failed", "no attempt made")
        for attempt in range(1, self._retry.attempts + 1):
            signed = sign_v4(
                method=method,
                url=url,
                headers=headers or {},
                payload_sha256=hashlib.sha256(body).hexdigest(),
                credentials=self._credentials,
                region=self._config.region,
                at=self._clock(),
            )
            try:
                response = self._http().request(
                    signed.method, signed.url, headers=signed.headers, content=body
                )
            except httpx.TransportError as exc:
                last_error = exc
                log.warning(
                    "attempt %d/%d %s %s: %s", attempt, self._retry.attempts, method, url, exc
                )
            else:
                if response.status_code < 500:
                    return response
                last_error = ObjectStoreError(
                    _error_code(response.content),
                    f"HTTP {response.status_code} from {method} {url}",
                )
                log.warning(
                    "attempt %d/%d %s %s: HTTP %d",
                    attempt,
                    self._retry.attempts,
                    method,
                    url,
                    response.status_code,
                )
            if attempt < self._retry.attempts:
                self._sleep(self._retry.delay(attempt, self._rng))
        if isinstance(last_error, ObjectStoreError):
            raise last_error
        raise ObjectStoreError("request_failed", f"{method} {url}: {last_error}") from last_error

    def _raise_unless(self, response: httpx.Response, ok: set[int], what: str) -> None:
        if response.status_code in ok:
            return
        raise ObjectStoreError(
            _error_code(response.content),
            f"HTTP {response.status_code} for {what!r} on {self._base}/{self.bucket}",
        )


def _parse_listing(body: bytes) -> tuple[list[ObjectInfo], str | None]:
    root = etree.fromstring(body, _XML_PARSER)
    if root is None or _local(root) != "ListBucketResult":
        raise ObjectStoreError("bad_listing", "response is not a ListBucketResult")
    page: list[ObjectInfo] = []
    for el in root:
        if not isinstance(el.tag, str) or _local(el) != "Contents":
            continue
        key = _child_text(el, "Key")
        if key is None:
            raise ObjectStoreError("bad_listing", "Contents without Key")
        page.append(
            ObjectInfo(
                key=key,
                size=int(_child_text(el, "Size") or "0"),
                etag=_child_text(el, "ETag"),
                last_modified=_child_text(el, "LastModified"),
            )
        )
    truncated = (_child_text(root, "IsTruncated") or "false").strip().lower() == "true"
    token = _child_text(root, "NextContinuationToken") if truncated else None
    if truncated and not token:
        raise ObjectStoreError("bad_listing", "IsTruncated without NextContinuationToken")
    return page, token
