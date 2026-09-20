"""01 §3 rule 2: T1 is the system of record; T2 copies are compared within tolerance."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from energy_platform.contracts.intervals import interval_for_index
from energy_platform.contracts.observation import EnergyObservation
from energy_platform.mapping.reconcile import TOLERANCES, compare_key, reconcile_transports

DAY = date(2026, 9, 17)


def row(metric: str, value: str | None, transport: str = "soap", **over: Any) -> EnergyObservation:
    unit = "EUR/MWh" if metric.startswith("price") else "MWh"
    base: dict[str, Any] = {
        "source_id": "ote",
        "dataset_id": "ote.idm_continuous",
        "source_transport": transport,
        "contract_version": "1.0.0",
        "derivation_id": "0123456789abcdef",
        "raw_ref": "bronze/blobs/aa/" + "a" * 64,
        "payload_sha256": "a" * 64,
        "fetched_at": datetime(2026, 9, 18, tzinfo=UTC),
        "source_published_at": None,
        "source_version": None,
        "processed_at": datetime(2026, 9, 18, tzinfo=UTC),
        "delivery_interval": interval_for_index(DAY, 1, "PT15M"),
        "resolution": "PT15M",
        "local_date": DAY,
        "period_index": 1,
        "kind": "interval",
        "dimensions": {"bidding_zone": "CZ"},
        "metric": metric,
        "value": None if value is None else Decimal(value),
        "unit": unit,
        "sign_convention": "as_published",
    }
    base.update(over)
    return EnergyObservation(**base)


def other(*rows: EnergyObservation) -> dict[Any, tuple[str, Decimal | None]]:
    return {compare_key(r): (r.source_transport, r.value) for r in rows}


def test_tolerances_are_the_01_values() -> None:
    assert TOLERANCES == {"EUR/MWh": Decimal("0.01"), "MWh": Decimal("0.001")}


def test_copy_within_tolerance_is_silent() -> None:
    t1 = row("price_vwap", "170.13")
    t2 = row("price_vwap", "170.135", transport="xlsx")
    assert reconcile_transports([t2], other(t1)) == ()
    assert reconcile_transports([t1], other(t2)) == ()


def test_copy_beyond_tolerance_raises_a_mismatch_in_both_directions() -> None:
    t1 = row("price_vwap", "170.13")
    t2 = row("price_vwap", "170.15", transport="xlsx")
    for doc, current in ((t2, t1), (t1, t2)):
        events = reconcile_transports([doc], other(current))
        assert [e.kind for e in events] == ["reconciliation_mismatch"]
        assert "soap=170.13 vs copy=170.15" in events[0].message
        assert events[0].metric == "price_vwap"


def test_volume_tolerance_is_a_thousandth() -> None:
    t1 = row("volume_total", "125.275")
    assert reconcile_transports([row("volume_total", "125.276", "xlsx")], other(t1)) == ()
    assert len(reconcile_transports([row("volume_total", "125.280", "xlsx")], other(t1))) == 1


def test_null_on_either_side_is_not_a_mismatch() -> None:
    assert (
        reconcile_transports([row("price_vwap", None, "xlsx")], other(row("price_vwap", "1"))) == ()
    )
    assert (
        reconcile_transports([row("price_vwap", "1", "xlsx")], other(row("price_vwap", None))) == ()
    )


def test_same_transport_or_no_counterpart_is_ignored() -> None:
    t1 = row("price_vwap", "170.13")
    assert reconcile_transports([t1], other(row("price_vwap", "999"))) == ()  # same transport
    assert reconcile_transports([t1], {}) == ()
    # T2-only metrics have an owner (xlsx) and no soap counterpart ever exists
    assert (
        reconcile_transports([row("price_min", "1", "xlsx")], other(row("price_min", "2", "xlsx")))
        == ()
    )
