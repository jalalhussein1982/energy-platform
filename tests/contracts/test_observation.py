"""EnergyObservation: envelope, time, identity, version identity (ADR-018, ADR-023, 01 §6/§8)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from energy_platform.contracts.intervals import DeliveryInterval, interval_for_index
from energy_platform.contracts.observation import (
    EnergyObservation,
    derivation_id,
    observation_identity,
    version_identity,
)

SHA = "a" * 64


def t1_row(**overrides: Any) -> EnergyObservation:
    base: dict[str, Any] = {
        "source_id": "ote",
        "dataset_id": "ote.idm_continuous",
        "source_transport": "soap",
        "contract_version": "1.0.0",
        "derivation_id": "0123456789abcdef",
        "raw_ref": "bronze/ote_idm_soap/2026/09/17/2026-09-17T00:00:00Z_1.xml",
        "payload_sha256": SHA,
        "fetched_at": datetime(2026, 9, 17, 0, 5, tzinfo=UTC),
        "source_published_at": None,
        "source_version": None,
        "processed_at": datetime(2026, 9, 17, 0, 6, tzinfo=UTC),
        "delivery_interval": interval_for_index(date(2026, 9, 17), 1, "PT15M"),
        "resolution": "PT15M",
        "local_date": date(2026, 9, 17),
        "period_index": 1,
        "kind": "interval",
        "dimensions": {"bidding_zone": "CZ"},
        "metric": "price_vwap",
        "value": Decimal("170.13"),
        "unit": "EUR/MWh",
        "sign_convention": "as_published",
    }
    base.update(overrides)
    return EnergyObservation(**base)


def test_valid_t1_row_builds() -> None:
    o = t1_row()
    assert o.delivery_start_utc == datetime(2026, 9, 16, 22, 0, tzinfo=UTC)
    assert o.delivery_end_utc == datetime(2026, 9, 16, 22, 15, tzinfo=UTC)
    assert o.value == Decimal("170.13")


def test_row_is_frozen_and_closed() -> None:
    o = t1_row()
    with pytest.raises(ValidationError):
        o.value = Decimal(1)
    with pytest.raises(ValidationError, match="extra"):
        t1_row(observed_at=datetime(2026, 1, 1, tzinfo=UTC))


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError, match="fetched_at"):
        t1_row(fetched_at=datetime(2026, 9, 17, 0, 5))  # noqa: DTZ001


def test_datetimes_normalised_to_utc() -> None:
    o = t1_row(fetched_at=datetime.fromisoformat("2026-09-17T02:05:00+02:00"))
    assert o.fetched_at == datetime(2026, 9, 17, 0, 5, tzinfo=UTC)
    assert o.fetched_at.tzinfo is UTC


def test_unregistered_dataset_rejected() -> None:
    with pytest.raises(ValidationError, match="not registered"):
        t1_row(dataset_id="ote.ida")


def test_unregistered_metric_rejected() -> None:
    with pytest.raises(ValidationError, match="price_median"):
        t1_row(metric="price_median")


def test_unit_must_match_registry() -> None:
    with pytest.raises(ValidationError, match="EUR/MWh"):
        t1_row(unit="MW")


def test_dimension_keys_must_match_identity_key() -> None:
    with pytest.raises(ValidationError, match="dimensions"):
        t1_row(dimensions={"area": "CZ"})
    with pytest.raises(ValidationError, match="dimensions"):
        t1_row(dimensions={"bidding_zone": "CZ", "extra": "x"})


def test_fixed_dimension_value_must_match_registry() -> None:
    with pytest.raises(ValidationError, match="bidding_zone"):
        t1_row(dimensions={"bidding_zone": "DE"})


def test_interval_length_must_match_resolution() -> None:
    with pytest.raises(ValidationError, match="resolution"):
        t1_row(resolution="PT60M")


def test_resolution_must_be_declared_by_dataset() -> None:
    iv = DeliveryInterval(
        datetime(2026, 9, 16, 22, tzinfo=UTC), datetime(2026, 9, 16, 22, 1, tzinfo=UTC)
    )
    with pytest.raises(ValidationError, match="PT1M"):
        t1_row(delivery_interval=iv, resolution="PT1M")


def test_source_id_must_match_dataset() -> None:
    with pytest.raises(ValidationError, match="source_id"):
        t1_row(source_id="ceps")


def test_bad_hashes_rejected() -> None:
    with pytest.raises(ValidationError, match="payload_sha256"):
        t1_row(payload_sha256="abc")
    with pytest.raises(ValidationError, match="derivation_id"):
        t1_row(derivation_id="ABCDEF0123456789")


def test_null_value_allowed() -> None:
    assert t1_row(value=None).value is None


def test_version_in_identity_requires_source_version() -> None:
    kwargs: dict[str, Any] = {
        "source_id": "ceps",
        "dataset_id": "ceps.load",
        "dimensions": {"area": "CZ", "aggregation_function": "AVG"},
        "metric": "load",
        "unit": "MW",
        "source_version": "RT",
    }
    o = t1_row(**kwargs)
    assert o.source_version == "RT"
    with pytest.raises(ValidationError, match="source_version"):
        t1_row(**{**kwargs, "source_version": None})
    with pytest.raises(ValidationError, match="aggregation_function"):
        t1_row(**{**kwargs, "dimensions": {"area": "CZ", "aggregation_function": "MAX"}})


def test_identity_tuples() -> None:
    o = t1_row()
    assert observation_identity(o) == (
        "ote.idm_continuous",
        (("bidding_zone", "CZ"),),
        datetime(2026, 9, 16, 22, 0, tzinfo=UTC),
        "PT15M",
        "price_vwap",
        None,
    )
    assert version_identity(o) == (*observation_identity(o), SHA, "0123456789abcdef")


def test_version_identity_axes_are_independent() -> None:
    base = t1_row()
    retry = t1_row()
    new_derivation = t1_row(derivation_id="fedcba9876543210")
    provider_correction = t1_row(payload_sha256="b" * 64)
    assert version_identity(base) == version_identity(retry)
    assert observation_identity(base) == observation_identity(new_derivation)
    assert version_identity(base) != version_identity(new_derivation)
    assert version_identity(base) != version_identity(provider_correction)
    assert version_identity(new_derivation) != version_identity(provider_correction)


def test_null_source_version_is_a_value_in_the_identity() -> None:
    assert observation_identity(t1_row()) == observation_identity(t1_row())


def test_derivation_id_shape_and_stability() -> None:
    mapping_a = {
        "metrics": {"price_vwap": {"source": "Price"}},
        "dimensions": {"bidding_zone": "CZ"},
    }
    mapping_b = {
        "dimensions": {"bidding_zone": "CZ"},
        "metrics": {"price_vwap": {"source": "Price"}},
    }
    d1 = derivation_id("0.1.0", "1.0.0", mapping_a, "generic:soap@0.1.0")
    d2 = derivation_id("0.1.0", "1.0.0", mapping_b, "generic:soap@0.1.0")
    assert re.fullmatch(r"[0-9a-f]{16}", d1)
    assert d1 == d2
    assert d1 != derivation_id("0.1.0", "1.0.0", mapping_a, "custom:" + "c" * 64)
    assert d1 != derivation_id("0.2.0", "1.0.0", mapping_a, "generic:soap@0.1.0")
    assert d1 != derivation_id("0.1.0", "1.1.0", mapping_a, "generic:soap@0.1.0")
    assert d1 != derivation_id("0.1.0", "1.0.0", {**mapping_a, "x": 1}, "generic:soap@0.1.0")
