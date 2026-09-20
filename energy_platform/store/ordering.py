"""Current-view selection rules shared by the memory store and the SQL view (ADR-023 §3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from energy_platform.contracts.observation import EnergyObservation


def semver_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def ordering_basis(o: EnergyObservation) -> Literal["source_published_at", "fetched_at"]:
    return "source_published_at" if o.source_published_at is not None else "fetched_at"


def ordering_instant(o: EnergyObservation) -> datetime:
    return o.source_published_at if o.source_published_at is not None else o.fetched_at


def rank(
    o: EnergyObservation, registered_at: datetime
) -> tuple[datetime, tuple[int, ...], datetime, str]:
    """Higher wins: ordering basis, contract semver, derivation registration, derivation id."""
    return (ordering_instant(o), semver_key(o.contract_version), registered_at, o.derivation_id)
