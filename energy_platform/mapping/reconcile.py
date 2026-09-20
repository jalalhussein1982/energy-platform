"""T1/T2 reconciliation (01 §3 rule 2): copies are stored and compared, never merged.

``price_vwap`` and ``volume_total`` may arrive from both transports. T1 (soap) is the system of
record; a T2 (xlsx) copy that differs by more than the tolerance raises a
``reconciliation_mismatch`` quality event. The comparison runs in both directions so that the
event is raised whichever document arrives second.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal

from energy_platform.contracts.observation import EnergyObservation
from energy_platform.contracts.registry import dataset
from energy_platform.mapping.quality import QualityEvent

TOLERANCES: Mapping[str, Decimal] = {"EUR/MWh": Decimal("0.01"), "MWh": Decimal("0.001")}

CompareKey = tuple[str, tuple[tuple[str, str], ...], datetime, str, str, str | None]
"""(dataset_id, dimensions, delivery_start_utc, resolution, metric, source_version)."""


def compare_key(o: EnergyObservation) -> CompareKey:
    return (
        o.dataset_id,
        tuple(sorted(o.dimensions.items())),
        o.delivery_start_utc,
        o.resolution,
        o.metric,
        o.source_version,
    )


def reconcile_transports(
    observations: Iterable[EnergyObservation],
    other_current: Mapping[CompareKey, tuple[str, Decimal | None]],
) -> tuple[QualityEvent, ...]:
    """Compare this document's rows with the *current* rows of the other transport.

    ``other_current`` maps a compare key to ``(source_transport, value)`` for rows of the same
    dataset delivered by a different transport. Only metrics that the registry marks as owned by
    one transport and delivered by another are compared.
    """
    events: list[QualityEvent] = []
    for o in observations:
        contract = dataset(o.dataset_id)
        spec = contract.metric(o.metric) if contract else None
        if spec is None or spec.owner_transport is None:
            continue
        other = other_current.get(compare_key(o))
        if other is None:
            continue
        other_transport, other_value = other
        if other_transport == o.source_transport:
            continue
        if o.value is None or other_value is None:
            continue
        tolerance = TOLERANCES.get(o.unit, Decimal(0))
        if abs(o.value - other_value) > tolerance:
            owner = spec.owner_transport
            record_value = o.value if o.source_transport == owner else other_value
            copy_value = other_value if o.source_transport == owner else o.value
            events.append(
                QualityEvent(
                    "reconciliation_mismatch",
                    "warning",
                    f"{o.metric} {o.delivery_start_utc:%Y-%m-%dT%H:%MZ}: "
                    f"{owner}={record_value} vs copy={copy_value} (tolerance {tolerance} {o.unit})",
                    metric=o.metric,
                )
            )
    return tuple(events)
