"""The canonical observation: destination side of the contract (ADR-011, ADR-018, ADR-023).

One ``EnergyObservation`` is **one metric value for one observation identity** (plan P1-D1):
Silver rows are metric-long, which is what lets 01 §3 assign ownership of a metric to one
transport. Field names are exactly those of ``docs/01-data-scope.md`` §6.1 (envelope) and §6.2
(time), plus ``derivation_id`` from ADR-023 and the per-metric fields of §9.

Three versions, three meanings (ADR-023 §1):

* ``source_version`` — the source's own revision marker, or ``None``;
* ``contract_version`` — semver of the registered dataset contract;
* ``derivation_id`` — identity of the implementation that produced the row.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from energy_platform.contracts.decimals import Sign
from energy_platform.contracts.intervals import DeliveryInterval, parse_duration
from energy_platform.contracts.registry import TIME_DIMENSIONS, Transport, dataset

ObservationKind = Literal["interval", "point"]

_SEMVER = r"^\d+\.\d+\.\d+$"
_SHA256 = r"^[0-9a-f]{64}$"
_DERIVATION = r"^[0-9a-f]{16}$"


class EnergyObservation(BaseModel):
    """Bitemporal canonical row. Frozen; unknown fields are an error, not a warning."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    # --- envelope (01 §6.1, ADR-023) -------------------------------------------------------
    source_id: str
    dataset_id: str
    source_transport: Transport
    contract_version: str = Field(pattern=_SEMVER)
    derivation_id: str = Field(pattern=_DERIVATION)
    raw_ref: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=_SHA256)
    fetched_at: AwareDatetime
    source_published_at: AwareDatetime | None
    source_version: str | None
    processed_at: AwareDatetime

    # --- time (01 §6.2) --------------------------------------------------------------------
    delivery_interval: DeliveryInterval
    resolution: str
    local_date: date
    period_index: int | None = Field(ge=1)
    kind: ObservationKind

    # --- identity and value (01 §6.3, §9) --------------------------------------------------
    dimensions: Mapping[str, str]
    metric: str
    value: Decimal | None
    unit: str
    sign_convention: Sign

    @property
    def delivery_start_utc(self) -> datetime:
        return self.delivery_interval.start

    @property
    def delivery_end_utc(self) -> datetime:
        return self.delivery_interval.end

    @field_validator("fetched_at", "source_published_at", "processed_at")
    @classmethod
    def _to_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else v.astimezone(UTC)

    @model_validator(mode="after")
    def _against_registry(self) -> EnergyObservation:
        contract = dataset(self.dataset_id)
        if contract is None:
            raise ValueError(f"dataset_id {self.dataset_id!r} is not registered (ADR-022 Route B)")
        if self.source_id != contract.source_id:
            raise ValueError(
                f"source_id {self.source_id!r} does not match registry {contract.source_id!r}"
            )
        spec = contract.metric(self.metric)
        if spec is None:
            raise ValueError(
                f"metric {self.metric!r} is not registered for {self.dataset_id} "
                f"(registered: {sorted(contract.metrics)})"
            )
        if self.unit != spec.unit:
            raise ValueError(
                f"unit {self.unit!r} for {self.metric} must be the registry unit {spec.unit!r}"
            )
        expected_dims = contract.manifest_dimensions()
        if tuple(sorted(self.dimensions)) != tuple(sorted(expected_dims)):
            raise ValueError(
                f"dimensions keys {sorted(self.dimensions)} must be exactly "
                f"{sorted(expected_dims)} (identity key minus {TIME_DIMENSIONS} and version)"
            )
        for key, fixed in contract.fixed_dimensions.items():
            if self.dimensions[key] != fixed:
                raise ValueError(f"dimension {key}={self.dimensions[key]!r} must be {fixed!r}")
        for key, allowed in contract.allowed_dimension_values.items():
            if self.dimensions[key] not in allowed:
                raise ValueError(f"dimension {key}={self.dimensions[key]!r} not in {allowed}")
        if contract.version_in_identity and self.source_version is None:
            raise ValueError(
                f"{self.dataset_id} carries `version` in its identity key: "
                "source_version is required"
            )
        if self.resolution not in contract.resolutions:
            raise ValueError(
                f"resolution {self.resolution!r} not declared for {self.dataset_id} "
                f"(declared: {contract.resolutions})"
            )
        if self.kind == "interval" and self.delivery_interval.duration != parse_duration(
            self.resolution
        ):
            raise ValueError(
                f"delivery interval length {self.delivery_interval.duration} "
                f"does not match resolution {self.resolution}"
            )
        return self


IdentityDims = tuple[tuple[str, str], ...]
ObservationIdentity = tuple[str, IdentityDims, datetime, str, str, str | None]
VersionIdentity = tuple[str, IdentityDims, datetime, str, str, str | None, str, str]


def observation_identity(o: EnergyObservation) -> ObservationIdentity:
    """01 §8: identity key ⊕ metric ⊕ ``source_version`` (``None`` is a value, ADR-023 §5)."""
    return (
        o.dataset_id,
        tuple(sorted(o.dimensions.items())),
        o.delivery_start_utc,
        o.resolution,
        o.metric,
        o.source_version,
    )


def version_identity(o: EnergyObservation) -> VersionIdentity:
    """ADR-023 §2: the upsert key. Same key ⇒ nothing is inserted."""
    return (*observation_identity(o), o.payload_sha256, o.derivation_id)


def derivation_id(
    platform_version: str,
    contract_version: str,
    mapping_block: Mapping[str, Any],
    parser_ref: str,
) -> str:
    """ADR-023 §1: first 16 hex of SHA-256 over the canonical JSON of the four components.

    ``parser_ref`` is ``generic:<parser-name>@<platform_version>`` or
    ``custom:<sha256 of targets/<id>/parser.py>``.
    """
    canonical = json.dumps(
        {
            "platform_version": platform_version,
            "contract_version": contract_version,
            "mapping_block": mapping_block,
            "parser_ref": parser_ref,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
