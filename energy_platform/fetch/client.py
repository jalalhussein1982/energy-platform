"""The fetcher: ADR-026 layer 2 around ``httpx`` (the only HTTP client, A-7).

Every request, including every redirect hop the fetcher follows by hand, is checked by
:mod:`energy_platform.fetch.policy` before a connection is made; the name is resolved here and
the connected peer is re-checked afterwards. Retries use capped exponential backoff with jitter
and never retry a 4xx. Conditional requests carry the previous capture's validators.
"""

from __future__ import annotations

import logging
import random
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx

from energy_platform.fetch.policy import (
    Destination,
    EgressError,
    check_addresses,
    check_peer,
    check_proxy_environment,
    check_url,
)
from energy_platform.fetch.secrets import redact_query

log = logging.getLogger("energy_platform.fetch")

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
USER_AGENT = "energy-platform/0.0.1 (+https://github.com/energy-platform; data ingestion)"


class Resolver(Protocol):
    def __call__(self, host: str, port: int) -> tuple[str, ...]: ...


def system_resolver(host: str, port: int) -> tuple[str, ...]:
    """Resolve with the system resolver; the fetch package is the only place this may happen."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise EgressError("unresolvable", f"{host!r}: {exc}") from exc
    return tuple(dict.fromkeys(str(info[4][0]) for info in infos))


@dataclass(frozen=True, slots=True)
class Conditional:
    """Validators from the previous capture of the same target (P2-D14)."""

    etag: str | None = None
    last_modified: str | None = None

    def headers(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.etag:
            out["If-None-Match"] = self.etag
        if self.last_modified:
            out["If-Modified-Since"] = self.last_modified
        return out


@dataclass(frozen=True, slots=True)
class FetchRequest:
    url: str
    method: str = "GET"
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None
    conditional: Conditional | None = None
    redact_params: tuple[str, ...] = ()
    """Query parameters whose values are secrets; redacted in every stored or logged URL."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    """Final URL after redirects, secrets redacted."""
    status: int
    headers: Mapping[str, str]
    body: bytes
    content_type: str | None
    fetched_at: datetime
    etag: str | None
    last_modified: str | None
    not_modified: bool
    hops: tuple[str, ...]


class FetchFailed(Exception):
    """The source answered, but not with a payload (non-2xx after retries)."""

    def __init__(self, status: int, url: str, body: bytes) -> None:
        super().__init__(f"HTTP {status} from {url}")
        self.status = status
        self.url = url
        self.body = body[:2048]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 4
    base_seconds: float = 0.5
    cap_seconds: float = 8.0
    jitter: float = 0.25

    def delay(self, attempt: int, rng: random.Random) -> float:
        """Delay before retry ``attempt`` (1-based): capped exponential with ± ``jitter``."""
        raw = min(self.cap_seconds, self.base_seconds * (2.0 ** (attempt - 1)))
        return raw * (1 + rng.uniform(-self.jitter, self.jitter))


DEFAULT_RETRY = RetryPolicy()


class RateLimiter:
    """Token bucket: at most ``requests`` per ``per_seconds``; sleeps when exhausted."""

    def __init__(
        self,
        requests: int,
        per_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._capacity = float(requests)
        self._rate = requests / per_seconds
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(requests)
        self._last = clock()

    def acquire(self) -> None:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens < 1:
            wait = (1 - self._tokens) / self._rate
            self._sleep(wait)
            self._tokens = 0.0
            self._last = self._clock()
        else:
            self._tokens -= 1


def _peer_of(response: httpx.Response) -> str | None:
    stream: Any = response.extensions.get("network_stream")
    if stream is None:
        return None
    info = stream.get_extra_info("server_addr")
    if not info:
        return None
    return str(info[0])


class Fetcher:
    """One instance per target run. ``offline=True`` is for fixture/mock transports (P2-D10)."""

    def __init__(
        self,
        *,
        allowed_hosts: tuple[str, ...],
        allow_insecure: bool = False,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = system_resolver,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        rng: random.Random | None = None,
        offline: bool = False,
        timeout: float = 30.0,
        max_redirects: int = 3,
        retry: RetryPolicy = DEFAULT_RETRY,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._allowed_hosts = allowed_hosts
        self._allow_insecure = allow_insecure
        self._transport = transport
        self._resolver = resolver
        self._sleep = sleep
        self._clock = clock
        self._rng = rng or random.SystemRandom()
        self._offline = offline
        self._timeout = timeout
        self._max_redirects = max_redirects
        self._retry = retry
        self._rate_limiter = rate_limiter
        self.proxies = check_proxy_environment()

    # ------------------------------------------------------------------ public

    def fetch(self, request: FetchRequest) -> FetchResult:
        hops: list[str] = []
        url = request.url
        method = request.method
        body = request.body
        headers = {"User-Agent": USER_AGENT, **request.headers}
        if request.conditional is not None:
            headers.update(request.conditional.headers())
        with self._client() as client:
            for _ in range(self._max_redirects + 1):
                destination = check_url(url, self._allowed_hosts, self._allow_insecure)
                resolved = self._resolve(destination)
                response = self._send_with_retries(client, method, url, headers, body)
                self._check_peer(destination, response, resolved)
                hops.append(redact_query(url, request.redact_params))
                if response.status_code in _REDIRECT_STATUSES and "location" in response.headers:
                    url = urljoin(url, response.headers["location"])
                    if response.status_code == 303 or (
                        response.status_code in {301, 302} and method == "POST"
                    ):
                        method, body = "GET", None
                    log.info("redirect %s -> %s", hops[-1], redact_query(url, ()))
                    continue
                return self._result(request, response, hops)
        raise EgressError(
            "too_many_redirects", f"more than {self._max_redirects} redirects from {hops[0]}"
        )

    # ------------------------------------------------------------------ internals

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self._transport,
            follow_redirects=False,
            timeout=self._timeout,
            trust_env=True,
        )

    def _resolve(self, destination: Destination) -> tuple[str, ...]:
        if self._offline:
            return ()
        return check_addresses(destination.host, self._resolver(destination.host, destination.port))

    def _check_peer(
        self, destination: Destination, response: httpx.Response, resolved: tuple[str, ...]
    ) -> None:
        if self._offline:
            return
        check_peer(destination.host, _peer_of(response), resolved)

    def _send_with_retries(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> httpx.Response:
        last_error: Exception = EgressError("fetch_error", "no attempt made")
        for attempt in range(1, self._retry.attempts + 1):
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()
            try:
                response = client.request(method, url, headers=dict(headers), content=body)
            except httpx.TransportError as exc:
                last_error = exc
                log.warning(
                    "attempt %d/%d %s %s: %s", attempt, self._retry.attempts, method, url, exc
                )
            else:
                if response.status_code < 500:
                    return response
                last_error = FetchFailed(response.status_code, url, response.content)
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
        if isinstance(last_error, FetchFailed):
            raise last_error
        raise EgressError("fetch_error", f"{method} {url}: {last_error}") from last_error

    def _result(
        self, request: FetchRequest, response: httpx.Response, hops: list[str]
    ) -> FetchResult:
        status = response.status_code
        if status == 304:
            not_modified = True
        elif 200 <= status < 300:
            not_modified = False
        else:
            raise FetchFailed(status, hops[-1], response.content)
        return FetchResult(
            url=hops[-1],
            status=status,
            headers=dict(response.headers),
            body=b"" if not_modified else response.content,
            content_type=response.headers.get("content-type"),
            fetched_at=self._clock(),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            not_modified=not_modified,
            hops=tuple(hops),
        )
