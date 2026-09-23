"""The fetcher against a mock transport: every ADR-026 §2 rule, retries, redirects, validators."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

import pytest

from energy_platform.fetch.client import (
    Conditional,
    Fetcher,
    FetchFailed,
    FetchRequest,
    RateLimiter,
    RetryPolicy,
)
from energy_platform.fetch.offline import (
    Handler,
    Request,
    Response,
    TransportError,
    mock_transport,
    response,
    streamed_response,
)
from energy_platform.fetch.policy import EgressError

OTE_IP = "91.209.101.45"
CEPS_IP = "150.171.109.193"


def respond(
    status: int = 200,
    body: bytes = b"ok",
    peer: str | None = OTE_IP,
    headers: dict[str, str] | None = None,
    **more: str,
) -> Response:
    return response(status, body, {**(headers or {}), **more}, peer=peer)


def resolver(host: str, port: int) -> tuple[str, ...]:
    return {"www.ote-cr.cz": (OTE_IP,), "www.ceps.cz": (CEPS_IP,)}.get(host, ())


def fetcher(handler: Handler, **kw: Any) -> Fetcher:
    slept: list[float] = kw.pop("slept", [])
    defaults: dict[str, Any] = {
        "allowed_hosts": ("www.ote-cr.cz", "www.ceps.cz"),
        "transport": mock_transport(handler),
        "resolver": resolver,
        "sleep": slept.append,
        "clock": lambda: datetime(2026, 9, 18, 0, 5, tzinfo=UTC),
        "rng": random.SystemRandom(),
    }
    defaults.update(kw)
    return Fetcher(**defaults)


def test_plain_get_records_final_url_status_validators_and_time() -> None:
    def h(req: Request) -> Response:
        return respond(
            body=b"<x/>", etag='"abc"', headers={"last-modified": "Thu, 17 Sep 2026 22:00:00 GMT"}
        )

    r = fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert (r.status, r.body, r.etag, r.last_modified) == (
        200,
        b"<x/>",
        '"abc"',
        "Thu, 17 Sep 2026 22:00:00 GMT",
    )
    assert r.url == "https://www.ote-cr.cz/a"
    assert r.fetched_at == datetime(2026, 9, 18, 0, 5, tzinfo=UTC)
    assert r.not_modified is False


def test_policy_runs_before_any_request_is_sent() -> None:
    calls: list[str] = []

    def h(req: Request) -> Response:
        calls.append(str(req.url))
        return respond()

    with pytest.raises(EgressError) as info:
        fetcher(h).fetch(FetchRequest("https://evil.example/x"))
    assert info.value.code == "host_not_allowed"
    assert calls == []


def test_private_resolution_blocks_before_contact() -> None:
    calls: list[str] = []

    def h(req: Request) -> Response:
        calls.append(str(req.url))
        return respond()

    with pytest.raises(EgressError) as info:
        fetcher(h, resolver=lambda host, port: ("10.0.0.1",)).fetch(
            FetchRequest("https://www.ote-cr.cz/a")
        )
    assert info.value.code == "private_address"
    assert calls == []


def test_peer_mismatch_aborts_even_after_a_200() -> None:
    with pytest.raises(EgressError) as info:
        fetcher(lambda req: respond(peer="10.9.9.9")).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "peer_mismatch"


def test_transport_without_peer_info_needs_offline_flag() -> None:
    with pytest.raises(EgressError) as info:
        fetcher(lambda req: respond(peer=None)).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "peer_unknown"
    r = fetcher(lambda req: respond(peer=None), offline=True).fetch(
        FetchRequest("https://www.ote-cr.cz/a")
    )
    assert r.status == 200


def test_redirect_is_followed_by_hand_and_every_hop_checked() -> None:
    def h(req: Request) -> Response:
        if req.url.path == "/a":
            return respond(302, location="https://www.ceps.cz/b")
        return respond(body=b"final", peer=CEPS_IP)

    r = fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert r.body == b"final"
    assert r.hops == ("https://www.ote-cr.cz/a", "https://www.ceps.cz/b")


def test_redirect_to_unlisted_host_fails() -> None:
    def h(req: Request) -> Response:
        return respond(302, location="https://attacker.example/b")

    with pytest.raises(EgressError) as info:
        fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "host_not_allowed"


def test_redirect_to_private_address_fails() -> None:
    def h(req: Request) -> Response:
        return respond(302, location="https://www.ceps.cz/b")

    def r(host: str, port: int) -> tuple[str, ...]:
        return (OTE_IP,) if host == "www.ote-cr.cz" else ("192.168.0.1",)

    with pytest.raises(EgressError) as info:
        fetcher(h, resolver=r).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "private_address"


def test_more_than_max_redirects_fails() -> None:
    def h(req: Request) -> Response:
        return respond(302, location="https://www.ote-cr.cz/again")

    with pytest.raises(EgressError) as info:
        fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "too_many_redirects"


def test_post_redirected_with_303_becomes_get_without_body() -> None:
    seen: list[tuple[str, bytes]] = []

    def h(req: Request) -> Response:
        seen.append((req.method, req.content))
        if req.url.path == "/soap":
            return respond(303, location="/moved")
        return respond()

    fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/soap", method="POST", body=b"<e/>"))
    assert seen == [("POST", b"<e/>"), ("GET", b"")]


def test_5xx_is_retried_with_capped_jittered_backoff_then_succeeds() -> None:
    attempts = {"n": 0}

    def h(req: Request) -> Response:
        attempts["n"] += 1
        return respond(503) if attempts["n"] < 3 else respond(body=b"late")

    slept: list[float] = []
    r = fetcher(h, slept=slept, retry=RetryPolicy(attempts=4, base_seconds=1, cap_seconds=8)).fetch(
        FetchRequest("https://www.ote-cr.cz/a")
    )
    assert r.body == b"late"
    assert attempts["n"] == 3
    assert len(slept) == 2
    assert 0.75 <= slept[0] <= 1.25 and 1.5 <= slept[1] <= 2.5


def test_backoff_delay_is_capped() -> None:
    rng = random.SystemRandom()
    p = RetryPolicy(base_seconds=0.5, cap_seconds=8.0, jitter=0.0)
    assert [p.delay(n, rng) for n in (1, 2, 3, 4, 5, 6)] == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]


def test_5xx_exhausting_attempts_raises_fetch_failed() -> None:
    slept: list[float] = []
    with pytest.raises(FetchFailed) as info:
        fetcher(lambda req: respond(502, body=b"bad gateway"), slept=slept).fetch(
            FetchRequest("https://www.ote-cr.cz/a")
        )
    assert info.value.status == 502
    assert len(slept) == 3  # 4 attempts, 3 waits


def test_4xx_is_not_retried() -> None:
    n = {"c": 0}

    def h(req: Request) -> Response:
        n["c"] += 1
        return respond(404, body=b"nope")

    with pytest.raises(FetchFailed) as info:
        fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert (info.value.status, n["c"]) == (404, 1)


def test_connection_errors_are_retried_then_reported_as_fetch_error() -> None:
    def h(req: Request) -> Response:
        raise TransportError("slow")

    with pytest.raises(EgressError) as info:
        fetcher(h, retry=RetryPolicy(attempts=2)).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "fetch_error"


def test_conditional_headers_and_304() -> None:
    sent: dict[str, str] = {}

    def h(req: Request) -> Response:
        sent.update({k: v for k, v in req.headers.items() if k.startswith("if-")})
        return respond(304, body=b"")

    cond = Conditional(etag='"abc"', last_modified="Thu, 17 Sep 2026 22:00:00 GMT")
    r = fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/a", conditional=cond))
    assert sent == {"if-none-match": '"abc"', "if-modified-since": "Thu, 17 Sep 2026 22:00:00 GMT"}
    assert r.not_modified is True and r.body == b""


def test_secret_query_parameter_is_redacted_in_the_result() -> None:
    r = fetcher(lambda req: respond()).fetch(
        FetchRequest(
            "https://www.ote-cr.cz/api?doc=A44&securityToken=s3cr3t",
            redact_params=("securityToken",),
        )
    )
    assert r.url == "https://www.ote-cr.cz/api?doc=A44&securityToken=%3Credacted%3E"
    assert "s3cr3t" not in r.url and "s3cr3t" not in str(r.hops)


def test_user_agent_identifies_the_platform() -> None:
    seen: dict[str, str] = {}

    def h(req: Request) -> Response:
        seen["ua"] = req.headers["user-agent"]
        return respond()

    fetcher(h).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert seen["ua"].startswith("energy-platform/")


def test_rate_limiter_sleeps_when_the_bucket_is_empty() -> None:
    now = {"t": 0.0}
    slept: list[float] = []

    def clock() -> float:
        return now["t"]

    def sleep(s: float) -> None:
        slept.append(s)
        now["t"] += s

    rl = RateLimiter(2, 60.0, clock=clock, sleep=sleep)
    rl.acquire()
    rl.acquire()
    rl.acquire()  # third within the same instant must wait 30 s for one token
    assert slept == [30.0]


# ----------------------------------------------------------------- 05 C-64: response-size cap


def test_declared_length_above_the_cap_is_refused_before_reading() -> None:
    n = {"c": 0}

    def h(req: Request) -> Response:
        n["c"] += 1
        return respond(200, body=b"x" * 2048)  # Content-Length 2048

    with pytest.raises(EgressError) as info:
        fetcher(h, max_body_bytes=1024).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "response_too_large"
    assert n["c"] == 1  # never retried


def test_streamed_body_without_a_length_is_counted_and_stopped() -> None:
    # a chunked answer (or a zip bomb's expansion) has no Content-Length to check up front
    n = {"c": 0}

    def h(req: Request) -> Response:
        n["c"] += 1
        return streamed_response(200, [b"x" * 600, b"y" * 600, b"z" * 600], peer=OTE_IP)

    with pytest.raises(EgressError) as info:
        fetcher(h, max_body_bytes=1024).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert info.value.code == "response_too_large"
    assert n["c"] == 1


def test_body_exactly_at_the_cap_is_accepted() -> None:
    r = fetcher(
        lambda req: streamed_response(200, [b"a" * 512, b"b" * 512], peer=OTE_IP),
        max_body_bytes=1024,
    ).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert r.body == b"a" * 512 + b"b" * 512


def test_error_body_is_read_to_2_kib_only() -> None:
    with pytest.raises(FetchFailed) as info:
        fetcher(
            lambda req: streamed_response(404, [b"e" * 1500, b"f" * 1500], peer=OTE_IP),
            max_body_bytes=1024,
        ).fetch(FetchRequest("https://www.ote-cr.cz/a"))
    assert (info.value.status, len(info.value.body)) == (404, 2048)


def test_default_cap_is_64_mib() -> None:
    f = fetcher(lambda req: respond(200, body=b"ok"))
    assert f._max_body_bytes == 64 * 1024 * 1024
