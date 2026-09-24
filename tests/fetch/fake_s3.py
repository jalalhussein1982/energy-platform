"""An in-memory S3 endpoint behind ``fetch.offline.mock_transport`` (P2-D20).

It checks what a real gateway would check before looking at the verb — path-style URL, the
``x-amz-content-sha256`` header against the body, the ``Authorization`` shape, ``x-amz-date`` and
``host`` — records every request, and answers with MinIO-shaped XML. A mismatch raises
``AssertionError`` straight out of the transport so a test fails at the offending request. No
socket is ever opened.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import unquote

from energy_platform.fetch.offline import (
    Request,
    Response,
    Transport,
    TransportError,
    mock_transport,
    response,
)

S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"
_AUTH = re.compile(
    r"^AWS4-HMAC-SHA256 Credential=(?P<ak>[A-Z0-9]+)/(?P<date>\d{8})/(?P<region>[a-z0-9-]+)"
    r"/s3/aws4_request, "
    r"SignedHeaders=(?P<signed>[a-z0-9;-]+), Signature=(?P<sig>[0-9a-f]{64})$"
)


@dataclass(slots=True)
class StoredObject:
    body: bytes
    content_type: str
    lock_mode: str | None = None
    retain_until: str | None = None
    storage_class: str | None = None

    @property
    def etag(self) -> str:
        return f'"{hashlib.md5(self.body, usedforsecurity=False).hexdigest()}"'


@dataclass(slots=True)
class FakeS3:
    bucket: str = "bronze"
    host: str = "minio.local:9000"
    access_key_id: str = "AKIAIOSFODNN7EXAMPLE"
    region: str = "us-east-1"
    max_keys: int = 1000
    """Server-side page cap, as S3's 1000: a client asking for more gets this many."""
    objects: dict[str, StoredObject] = field(default_factory=dict)
    requests: list[Request] = field(default_factory=list)
    faults: list[int | None] = field(default_factory=list)
    """Consumed first: an HTTP status to answer with, or ``None`` for a connection error."""
    storage_classes: frozenset[str] = frozenset({"STANDARD"})
    """Classes the gateway implements. Any other ``x-amz-storage-class`` on a PUT answers
    ``400 InvalidArgument`` with an **empty** ``<Message>``, as Ceph RGW does (V-6, V-12)."""
    honours_if_none_match: bool = True
    """``If-None-Match: *`` on a PUT answers 412 when the key exists (MinIO, Ceph RGW); a
    gateway that ignores the header keeps the last writer (review 2 DC-06 residual)."""
    after_put: Callable[[str], None] | None = None
    """Test hook run after a successful PUT (a concurrent writer overwriting the key)."""

    def transport(self) -> Transport:
        return mock_transport(self.handle)

    # ------------------------------------------------------------------ recording helpers

    def calls(self) -> list[tuple[str, str]]:
        """``(method, path-with-query)`` in order."""
        return [(r.method, str(r.url.raw_path, "ascii")) for r in self.requests]

    # ------------------------------------------------------------------ the gateway

    def handle(self, request: Request) -> Response:
        self.requests.append(request)
        self._check_signature_shape(request)
        if self.faults:
            fault = self.faults.pop(0)
            if fault is None:
                raise TransportError("connection reset by the fake gateway")
            return _error(fault, "InternalError", "injected")
        path = unquote(request.url.path)
        prefix = f"/{self.bucket}"
        assert path == prefix or path.startswith(prefix + "/"), (
            f"not path-style for bucket {self.bucket!r}: {path!r}"
        )
        key = path[len(prefix) + 1 :]
        if request.method == "GET" and not key:
            return self._list(request)
        assert key, f"{request.method} on the bucket root"
        if request.method == "PUT":
            return self._put(key, request)
        if request.method == "GET":
            return self._get(key)
        if request.method == "HEAD":
            return self._head(key)
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return response(204)
        raise AssertionError(f"unexpected verb {request.method}")

    def _check_signature_shape(self, request: Request) -> None:
        payload = hashlib.sha256(request.content).hexdigest()
        assert request.headers.get("x-amz-content-sha256") == payload, "payload hash not signed"
        assert re.fullmatch(r"\d{8}T\d{6}Z", request.headers.get("x-amz-date", "")), "x-amz-date"
        assert request.headers.get("host") == self.host, request.headers.get("host")
        auth = _AUTH.match(request.headers.get("authorization", ""))
        assert auth is not None, f"authorization header: {request.headers.get('authorization')!r}"
        assert auth["ak"] == self.access_key_id and auth["region"] == self.region
        assert auth["date"] == request.headers["x-amz-date"][:8]
        signed = auth["signed"].split(";")
        assert signed == sorted(signed)
        for name in ("host", "x-amz-content-sha256", "x-amz-date"):
            assert name in signed, f"{name} must be a signed header"
        for name in signed:
            assert name in request.headers, f"signed header {name} not sent"

    def _put(self, key: str, request: Request) -> Response:
        lock_mode = request.headers.get("x-amz-object-lock-mode")
        retain_until = request.headers.get("x-amz-object-lock-retain-until-date")
        if (lock_mode or retain_until) and "content-md5" not in request.headers:
            return _error(400, "InvalidRequest", "Content-MD5 is required with Object Lock")
        storage_class = request.headers.get("x-amz-storage-class")
        if storage_class is not None and storage_class not in self.storage_classes:
            return _error(400, "InvalidArgument", "")
        if (
            self.honours_if_none_match
            and request.headers.get("if-none-match") == "*"
            and key in self.objects
        ):
            return _error(
                412,
                "PreconditionFailed",
                "At least one of the pre-conditions you specified did not hold",
            )
        obj = StoredObject(
            body=bytes(request.content),
            content_type=request.headers.get("content-type", "binary/octet-stream"),
            lock_mode=lock_mode,
            retain_until=retain_until,
            storage_class=storage_class,
        )
        self.objects[key] = obj
        if self.after_put is not None:
            self.after_put(key)
        return response(200, b"", {"etag": obj.etag})

    def _get(self, key: str) -> Response:
        obj = self.objects.get(key)
        if obj is None:
            return _error(404, "NoSuchKey", "The specified key does not exist.")
        return response(200, obj.body, _object_headers(obj))

    def _head(self, key: str) -> Response:
        obj = self.objects.get(key)
        if obj is None:
            return response(404)
        return response(200, b"", _object_headers(obj))

    def _list(self, request: Request) -> Response:
        params = request.url.params
        assert params.get("list-type") == "2", "ListObjectsV2 only"
        prefix = params.get("prefix", "")
        max_keys = min(int(params.get("max-keys", "1000")), self.max_keys)
        token = params.get("continuation-token")
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        if token is not None:
            keys = [k for k in keys if k > token]
        page, rest = keys[:max_keys], keys[max_keys:]
        contents = "".join(
            f"<Contents><Key>{k}</Key><LastModified>2026-09-20T10:00:00.000Z</LastModified>"
            f"<ETag>{self.objects[k].etag.replace('"', '&quot;')}</ETag>"
            f"<Size>{len(self.objects[k].body)}</Size><StorageClass>STANDARD</StorageClass></Contents>"
            for k in page
        )
        truncated = "true" if rest else "false"
        next_token = f"<NextContinuationToken>{page[-1]}</NextContinuationToken>" if rest else ""
        body = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<ListBucketResult xmlns="{S3_NS}"><Name>{self.bucket}</Name><Prefix>{prefix}</Prefix>'
            f"<KeyCount>{len(page)}</KeyCount><MaxKeys>{max_keys}</MaxKeys>"
            f"<IsTruncated>{truncated}</IsTruncated>{next_token}{contents}</ListBucketResult>"
        )
        return response(200, body.encode(), {"content-type": "application/xml"})


def _object_headers(obj: StoredObject) -> dict[str, str]:
    headers = {
        "content-length": str(len(obj.body)),
        "content-type": obj.content_type,
        "etag": obj.etag,
        "last-modified": "Sun, 20 Sep 2026 10:00:00 GMT",
    }
    if obj.lock_mode:
        headers["x-amz-object-lock-mode"] = obj.lock_mode
    if obj.retain_until:
        headers["x-amz-object-lock-retain-until-date"] = obj.retain_until
    if obj.storage_class and obj.storage_class != "STANDARD":
        headers["x-amz-storage-class"] = obj.storage_class
    return headers


def _error(status: int, code: str, message: str) -> Response:
    body = (
        f'<?xml version="1.0" encoding="UTF-8"?><Error><Code>{code}</Code>'
        f"<Message>{message}</Message><Resource>/</Resource><RequestId>fake</RequestId></Error>"
    )
    return response(status, body.encode(), {"content-type": "application/xml"})
