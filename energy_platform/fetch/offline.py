"""Offline transports: fixtures and tests never touch the network (ADR-010, ADR-020, P2-D10).

Only this package may import ``httpx``; tests and the CLI's ``--fixture`` path build their
transports here. A :class:`FixtureTransport` answers every request with one recorded payload,
which is how a Bronze fixture is replayed through the real fetch code path.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping

import httpx

Request = httpx.Request
Response = httpx.Response
Transport = httpx.BaseTransport
Handler = Callable[[httpx.Request], httpx.Response]


def mock_transport(handler: Handler) -> httpx.BaseTransport:
    """A transport that calls ``handler`` in-process. No socket is ever opened."""
    return httpx.MockTransport(handler)


def response(
    status: int = 200,
    body: bytes = b"",
    headers: Mapping[str, str] | None = None,
    *,
    peer: str | None = None,
) -> httpx.Response:
    """Build a response; ``peer`` fakes the connected address a real stream would report."""
    extensions = {"network_stream": _Stream(peer)} if peer is not None else {}
    return httpx.Response(status, content=body, headers=dict(headers or {}), extensions=extensions)


def streamed_response(
    status: int = 200,
    chunks: Iterable[bytes] = (),
    headers: Mapping[str, str] | None = None,
    *,
    peer: str | None = None,
) -> httpx.Response:
    """A response whose body arrives in ``chunks`` with no ``Content-Length`` (chunked, or a
    server that does not say): the fetch cap must count it as it streams (05 C-64)."""
    extensions = {"network_stream": _Stream(peer)} if peer is not None else {}
    return httpx.Response(
        status,
        headers=dict(headers or {}),
        stream=_ChunkStream(tuple(chunks)),
        extensions=extensions,
    )


class _ChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks


class _Stream:
    def __init__(self, addr: str) -> None:
        self._addr = addr

    def get_extra_info(self, name: str) -> tuple[str, int] | None:
        return (self._addr, 443) if name == "server_addr" else None


class FixtureTransport(httpx.BaseTransport):
    """Serve one recorded payload for every request; records what was asked."""

    def __init__(
        self, body: bytes, *, status: int = 200, content_type: str = "application/octet-stream"
    ) -> None:
        self._body = body
        self._status = status
        self._content_type = content_type
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            self._status, content=self._body, headers={"content-type": self._content_type}
        )


TransportError = httpx.TransportError
"""Raised by a handler to simulate a connection failure (retried by the fetcher)."""
