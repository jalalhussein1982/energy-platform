"""Host registry seeded from 01 §3 (ADR-026 §2)."""

from __future__ import annotations

from energy_platform.contracts.hosts import HOSTS, host


def test_committed_hosts_only() -> None:
    assert set(HOSTS) == {"www.ote-cr.cz", "www.ceps.cz"}


def test_lookup_is_case_insensitive_and_exact() -> None:
    e = host("WWW.OTE-CR.CZ")
    assert e is not None
    assert e.host == "www.ote-cr.cz"
    assert e.ports == (443,)
    assert host("ote-cr.cz") is None
    assert host("evil.www.ote-cr.cz") is None


def test_unadmitted_hosts_absent() -> None:
    assert host("web-api.tp.entsoe.eu") is None
    assert host("169.254.169.254") is None


def test_no_host_allows_insecure_or_other_ports() -> None:
    for e in HOSTS.values():
        assert e.allow_insecure is False
        assert e.ports == (443,)
