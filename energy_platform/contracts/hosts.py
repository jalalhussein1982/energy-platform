"""Host registry: the only destinations the fetch layer may connect to (ADR-026 §2, ADR-022).

A manifest's ``allowed_hosts`` must be a subset of this registry; the fetch layer (Phase 2)
checks both. Adding a host is a Route B platform PR under CODEOWNERS. Entries are exact
hostnames, lowercase, no wildcards, no IP addresses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class HostEntry:
    host: str
    ports: tuple[int, ...] = (443,)
    allow_insecure: bool = False
    """``True`` lets a manifest that also sets ``allow_insecure: true`` use ``http``."""
    note: str = ""


HOSTS: Mapping[str, HostEntry] = MappingProxyType(
    {
        e.host: e
        for e in (
            HostEntry("www.ote-cr.cz", note="T1/T2/E1 — OTE public web service and XLSX (01 §3)"),
            HostEntry("www.ceps.cz", note="T3 — ČEPS CepsData web service (01 §3)"),
        )
    }
)


def host(name: str) -> HostEntry | None:
    """Exact, case-insensitive lookup; ``None`` means the host is not admitted."""
    return HOSTS.get(name.strip().lower())
