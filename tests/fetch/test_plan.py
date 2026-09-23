"""Manifest fetch blocks → requests: SOAP body rendering, T2 discovery, REST auth via secretRef."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from energy_platform.contracts.manifest import Manifest, SecretRef, load_manifest
from energy_platform.fetch.client import Fetcher, FetchRequest
from energy_platform.fetch.offline import Request, Response, mock_transport
from energy_platform.fetch.plan import discover_link, fetch_for_manifest, soap_request
from energy_platform.fetch.policy import EgressError
from energy_platform.fetch.render import FetchContext
from energy_platform.fetch.secrets import (
    EnvSecretResolver,
    ScopedSecretResolver,
    SecretMissing,
    SecretOutOfScope,
    env_name,
)
from tests.contracts.manifest_fixtures import t1_manifest

EXAMPLES = Path("examples/manifests")
CTX = FetchContext.for_run(datetime(2026, 9, 18, 6, 0, tzinfo=UTC))


def offline_fetcher(handler: Any, manifest: Manifest) -> Fetcher:
    return Fetcher(
        allowed_hosts=manifest.allowed_hosts,
        allow_insecure=manifest.allow_insecure,
        transport=mock_transport(handler),
        offline=True,
        sleep=lambda s: None,
        rng=random.SystemRandom(),
    )


def test_soap_request_renders_params_then_body_and_sets_soap_11_headers() -> None:
    m = Manifest.model_validate(t1_manifest())
    assert m.fetch.soap_xml is not None
    req = soap_request(m.fetch.soap_xml, CTX)
    assert req.method == "POST"
    assert (
        req.headers["SOAPAction"]
        == '"http://www.ote-cr.cz/schema/service/public/GetImPricePeriodE"'
    )
    assert req.headers["Content-Type"].startswith("text/xml")
    assert req.body is not None
    assert b"<pub:StartDate>2026-09-18</pub:StartDate>" in req.body
    assert b"{" not in req.body


def test_t1_example_fetches_through_the_planner() -> None:
    m = load_manifest(EXAMPLES / "ote_idm_soap.yaml")
    seen: list[Request] = []

    def h(req: Request) -> Response:
        seen.append(req)
        return Response(200, content=b"<Envelope/>")

    r = fetch_for_manifest(m, CTX, offline_fetcher(h, m))
    assert r.body == b"<Envelope/>"
    assert seen[0].url.path == "/pw-data/services/PublicDataService"
    assert b"<pub:EndDate>2026-09-18</pub:EndDate>" in seen[0].content


def test_discovery_picks_the_first_matching_href_absolutised() -> None:
    page = (
        '<a href="/other.pdf">x</a>'
        '<a href="/pubweb/attachments/27/2026/month09/day18/IM_15MIN_18_09_2026_EN.xlsx">xlsx</a>'
    )
    url = discover_link(
        page,
        "https://www.ote-cr.cz/en/short-term-markets/x",
        r"IM_15MIN_\d{2}_\d{2}_\d{4}_EN\.xlsx",
    )
    assert (
        url
        == "https://www.ote-cr.cz/pubweb/attachments/27/2026/month09/day18/IM_15MIN_18_09_2026_EN.xlsx"
    )
    assert discover_link("<a href='/nothing'>", "https://www.ote-cr.cz/", r"\.xlsx") is None


def test_t2_uses_discovery_then_downloads_and_falls_back_when_no_link() -> None:
    m = load_manifest(EXAMPLES / "ote_idm_xlsx.yaml")
    calls: list[str] = []

    def with_link(req: Request) -> Response:
        calls.append(str(req.url))
        if req.url.path.startswith("/en/"):
            return Response(200, content=b'<a href="/pubweb/x/IM_15MIN_18_09_2026_EN.xlsx">f</a>')
        return Response(200, content=b"PK-xlsx")

    r = fetch_for_manifest(m, CTX, offline_fetcher(with_link, m))
    assert r.body == b"PK-xlsx"
    assert calls[1] == "https://www.ote-cr.cz/pubweb/x/IM_15MIN_18_09_2026_EN.xlsx"

    calls.clear()

    def without_link(req: Request) -> Response:
        calls.append(str(req.url))
        return Response(200, content=b"<html>no link</html>" if "/en/" in req.url.path else b"PK")

    fetch_for_manifest(m, CTX, offline_fetcher(without_link, m))
    assert calls[1] == (
        "https://www.ote-cr.cz/pubweb/attachments/27/2026/month09/day18/IM_15MIN_18_09_2026_EN.xlsx"
    )


def test_discovered_link_on_an_unlisted_host_is_refused() -> None:
    m = load_manifest(EXAMPLES / "ote_idm_xlsx.yaml")

    def h(req: Request) -> Response:
        return Response(
            200, content=b'<a href="https://evil.example/IM_15MIN_18_09_2026_EN.xlsx">f</a>'
        )

    with pytest.raises(EgressError) as info:
        fetch_for_manifest(m, CTX, offline_fetcher(h, m))
    assert info.value.code == "host_not_allowed"


def test_rest_auth_from_secret_ref_is_sent_but_never_stored() -> None:
    m = load_manifest(EXAMPLES / "entsoe_rest_xml.yaml")
    assert m.fetch.rest_xml is not None and m.fetch.rest_xml.auth is not None
    ref = m.fetch.rest_xml.auth.secretRef
    secrets = EnvSecretResolver({env_name(ref): "tok-123456"})
    seen: dict[str, str] = {}

    def h(req: Request) -> Response:
        seen["url"] = str(req.url)
        return Response(200, content=b"<x/>")

    # ENTSO-E is unadmitted: the registry check must refuse the host before any request.
    with pytest.raises(EgressError) as info:
        fetch_for_manifest(m, CTX, offline_fetcher(h, m), secrets=secrets)
    assert info.value.code == "host_not_registered"
    assert seen == {}


def test_rest_request_shape_with_a_registered_host() -> None:
    """Same block shape as ENTSO-E, but pointed at a registered host to exercise the REST path."""
    data = load_manifest(EXAMPLES / "entsoe_rest_xml.yaml").model_dump(mode="json")
    data["allowed_hosts"] = ["www.ote-cr.cz"]
    data["fetch"]["rest_xml"]["url_template"] = "https://www.ote-cr.cz/api"
    m = Manifest.model_validate(data)
    assert m.fetch.rest_xml is not None and m.fetch.rest_xml.auth is not None
    ref = m.fetch.rest_xml.auth.secretRef
    seen: dict[str, str] = {}

    def h(req: Request) -> Response:
        seen["url"] = str(req.url)
        return Response(200, content=b"<x/>")

    r = fetch_for_manifest(
        m, CTX, offline_fetcher(h, m), secrets=EnvSecretResolver({env_name(ref): "tok-123456"})
    )
    assert "tok-123456" in seen["url"]  # sent to the source
    assert "tok-123456" not in r.url  # never stored
    assert "%3Credacted%3E" in r.url


def test_missing_secret_stops_before_any_request() -> None:
    data = load_manifest(EXAMPLES / "entsoe_rest_xml.yaml").model_dump(mode="json")
    data["allowed_hosts"] = ["www.ote-cr.cz"]
    data["fetch"]["rest_xml"]["url_template"] = "https://www.ote-cr.cz/api"
    m = Manifest.model_validate(data)
    calls: list[str] = []

    def h(req: Request) -> Response:
        calls.append(str(req.url))
        return Response(200)

    with pytest.raises(SecretMissing):
        fetch_for_manifest(m, CTX, offline_fetcher(h, m), secrets=EnvSecretResolver({}))
    with pytest.raises(LookupError):
        fetch_for_manifest(m, CTX, offline_fetcher(h, m))
    assert calls == []


def test_fetch_request_defaults() -> None:
    r = FetchRequest("https://www.ote-cr.cz/a")
    assert (r.method, r.body, r.conditional, r.redact_params) == ("GET", None, None, ())


def test_scoped_resolver_refuses_a_platform_or_another_targets_secret() -> None:
    # 05 C-63: whatever the manifest says, a target resolves only target-<id>/<key>
    env = {
        "BRONZE_SECRET_ACCESS_KEY": "platform-secret",
        "TARGET_OTE_DAM_TOKEN": "dam-token",
        "TARGET_OTE_INTRADAY_MARKET_TOKEN": "own-token",
    }
    scoped = ScopedSecretResolver("ote_intraday_market", EnvSecretResolver(env))
    for name, key in (("BRONZE", "secret-access-key"), ("target-ote-dam", "token")):
        with pytest.raises(SecretOutOfScope):
            scoped.resolve(SecretRef(name=name, key=key))
    assert scoped.resolve(SecretRef(name="target-ote-intraday-market", key="token")) == "own-token"


def test_unvalidated_manifest_naming_a_platform_secret_sends_nothing() -> None:
    """A manifest that never went through validation still cannot reach BRONZE_*."""
    good = load_manifest(EXAMPLES / "entsoe_rest_xml.yaml").model_dump(mode="json")
    good["allowed_hosts"] = ["www.ote-cr.cz"]
    good["fetch"]["rest_xml"]["url_template"] = "https://www.ote-cr.cz/api"
    m = Manifest.model_validate(good)
    assert m.fetch.rest_xml is not None and m.fetch.rest_xml.auth is not None
    auth = m.fetch.rest_xml.auth.model_construct(
        secretRef=SecretRef(name="BRONZE", key="secret-access-key"),
        location="query",
        param="securityToken",
    )
    rest = m.fetch.rest_xml.model_copy(update={"auth": auth})
    crafted = m.model_copy(update={"fetch": m.fetch.model_copy(update={"rest_xml": rest})})
    seen: list[str] = []

    def h(req: Request) -> Response:
        seen.append(str(req.url))
        return Response(200, content=b"<x/>")

    secrets = EnvSecretResolver({"BRONZE_SECRET_ACCESS_KEY": "platform-secret"})
    with pytest.raises(SecretOutOfScope):
        fetch_for_manifest(crafted, CTX, offline_fetcher(h, crafted), secrets=secrets)
    assert seen == []
