"""Current-view selection rules shared by the memory store and the SQL view (ADR-023 §3,
amendment 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from energy_platform.contracts.observation import EnergyObservation
from energy_platform.contracts.registry import Transport, dataset


def semver_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def ordering_basis(o: EnergyObservation) -> Literal["source_published_at", "fetched_at"]:
    return "source_published_at" if o.source_published_at is not None else "fetched_at"


def ordering_instant(o: EnergyObservation) -> datetime:
    return o.source_published_at if o.source_published_at is not None else o.fetched_at


def owner_transport_of(o: EnergyObservation) -> Transport | None:
    """The transport the registry names as the system of record for this row's metric
    (01 §3 rule 2), or ``None`` when the metric has no owner. Stored on the row by the store
    (``observations.owner_transport``), never supplied by a mapping."""
    contract = dataset(o.dataset_id)
    spec = contract.metric(o.metric) if contract is not None else None
    return None if spec is None else spec.owner_transport


def owner_rank(o: EnergyObservation) -> int:
    """1 when this row comes from the owning transport (or the metric has no owner), else 0.
    Review 2 DC-03: the reconciliation copy never outranks the system of record."""
    owner = owner_transport_of(o)
    return 1 if owner is None or o.source_transport == owner else 0


def rank(
    o: EnergyObservation, registered_at: datetime
) -> tuple[int, datetime, tuple[int, ...], datetime, str]:
    """Higher wins: owner first (amendment 1), then ordering basis, contract semver, derivation
    registration, derivation id."""
    return (
        owner_rank(o),
        ordering_instant(o),
        semver_key(o.contract_version),
        registered_at,
        o.derivation_id,
    )
