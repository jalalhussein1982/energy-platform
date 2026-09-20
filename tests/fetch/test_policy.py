"""ADR-026 §2: scheme, host (manifest and registry), port, resolved address, peer, proxy."""

from __future__ import annotations

import pytest

from energy_platform.fetch.policy import (
    EgressError,
    check_addresses,
    check_peer,
    check_proxy_environment,
    check_url,
)

OTE = ("www.ote-cr.cz",)


def _code(fn: object, *args: object) -> str:
    with pytest.raises(EgressError) as info:
        fn(*args)  # type: ignore[operator]
    return info.value.code


def test_registered_https_host_on_443_is_accepted() -> None:
    d = check_url("https://www.ote-cr.cz/pw-data/services/PublicDataService", OTE, False)
    assert (d.scheme, d.host, d.port) == ("https", "www.ote-cr.cz", 443)


def test_host_not_in_manifest_allowlist() -> None:
    assert _code(check_url, "https://www.ceps.cz/x", OTE, False) == "host_not_allowed"


def test_host_in_manifest_but_not_in_registry() -> None:
    hosts = ("web-api.tp.entsoe.eu",)
    assert (
        _code(check_url, "https://web-api.tp.entsoe.eu/api", hosts, False) == "host_not_registered"
    )


def test_http_without_manifest_flag() -> None:
    assert _code(check_url, "http://www.ote-cr.cz/x", OTE, False) == "insecure_scheme"


def test_http_with_manifest_flag_but_registry_forbids() -> None:
    assert _code(check_url, "http://www.ote-cr.cz/x", OTE, True) == "insecure_host_not_registered"


def test_port_not_in_registry() -> None:
    assert _code(check_url, "https://www.ote-cr.cz:8080/x", OTE, False) == "port_not_allowed"


def test_ip_literal_never_a_destination() -> None:
    assert _code(check_url, "https://91.209.101.45/x", ("91.209.101.45",), False) == "ip_literal"


def test_other_schemes_rejected() -> None:
    assert _code(check_url, "ftp://www.ote-cr.cz/x", OTE, False) == "insecure_scheme"


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "172.16.5.5",
        "192.168.1.1",
        "169.254.169.254",
        "127.0.0.1",
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104 — the point of the test is that this address is refused
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:10.0.0.1",
    ],
)
def test_private_and_metadata_addresses_rejected(address: str) -> None:
    assert _code(check_addresses, "www.ote-cr.cz", (address,)) == "private_address"


def test_public_addresses_pass_through() -> None:
    assert check_addresses("www.ote-cr.cz", ("91.209.101.45", "2a02::1")) == (
        "91.209.101.45",
        "2a02::1",
    )


def test_one_private_address_among_public_ones_rejects() -> None:
    assert _code(check_addresses, "h", ("91.209.101.45", "10.1.1.1")) == "private_address"


def test_unresolvable_name() -> None:
    assert _code(check_addresses, "h", ()) == "unresolvable"


def test_peer_must_be_a_resolved_address() -> None:
    check_peer("h", "91.209.101.45", ("91.209.101.45",))
    assert _code(check_peer, "h", "10.0.0.9", ("91.209.101.45",)) == "peer_mismatch"
    assert _code(check_peer, "h", None, ("91.209.101.45",)) == "peer_unknown"


def test_proxy_environment_is_honoured_but_metadata_proxy_is_refused() -> None:
    assert check_proxy_environment({}) == ()
    assert check_proxy_environment({"HTTPS_PROXY": "http://proxy.corp:3128"}) == (
        "http://proxy.corp:3128",
    )
    with pytest.raises(EgressError, match="metadata"):
        check_proxy_environment({"HTTP_PROXY": "http://169.254.169.254:80"})
