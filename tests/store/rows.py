"""Row builders shared by the store tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from energy_platform.contracts.intervals import interval_for_index
from energy_platform.contracts.observation import EnergyObservation
from energy_platform.store import Derivation

DAY = date(2026, 9, 17)
T0 = datetime(2026, 9, 17, 22, 0, tzinfo=UTC)
FETCH_1 = datetime(2026, 9, 18, 0, 5, tzinfo=UTC)
FETCH_2 = FETCH_1 + timedelta(minutes=15)
D_A = Derivation("aaaaaaaaaaaaaaaa", "0.0.1", "1.0.0", {"m": "a"}, "generic:soap@0.0.1")
D_B = Derivation("bbbbbbbbbbbbbbbb", "0.0.1", "1.0.0", {"m": "b"}, "generic:soap@0.0.1")
SHA_1 = "1" * 64
SHA_2 = "2" * 64


def obs(
    metric: str = "price_vwap",
    value: str | None = "170.13",
    *,
    period: int = 1,
    sha: str = SHA_1,
    derivation: Derivation = D_A,
    fetched_at: datetime = FETCH_1,
    transport: str = "soap",
    published: datetime | None = None,
    source_version: str | None = None,
    dataset_id: str = "ote.idm_continuous",
    **over: Any,
) -> EnergyObservation:
    unit = (
        "EUR/MWh" if metric.startswith("price") else ("MW" if metric.startswith("load") else "MWh")
    )
    base: dict[str, Any] = {
        "source_id": dataset_id.split(".")[0],
        "dataset_id": dataset_id,
        "source_transport": transport,
        "contract_version": derivation.contract_version,
        "derivation_id": derivation.derivation_id,
        "raw_ref": f"bronze/blobs/{sha[:2]}/{sha}",
        "payload_sha256": sha,
        "fetched_at": fetched_at,
        "source_published_at": published,
        "source_version": source_version,
        "processed_at": fetched_at + timedelta(minutes=1),
        "delivery_interval": interval_for_index(DAY, period, "PT15M"),
        "resolution": "PT15M",
        "local_date": DAY,
        "period_index": period,
        "kind": "interval",
        "dimensions": {"bidding_zone": "CZ"},
        "metric": metric,
        "value": None if value is None else Decimal(value),
        "unit": unit,
        "sign_convention": "as_published",
    }
    base.update(over)
    return EnergyObservation(**base)
