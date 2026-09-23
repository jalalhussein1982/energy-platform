"""Dataset registry seeded from 01 §6.3 / §9 (ADR-022)."""

from __future__ import annotations

import re

from energy_platform.contracts.registry import DATASETS, DatasetContract, dataset

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_only_admitted_datasets_are_registered() -> None:
    # the committed targets' three, plus the held-out source admitted by Route B (ADR-022 §3)
    assert set(DATASETS) == {
        "ote.idm_continuous",
        "ote.dam",
        "ceps.load",
        "ote.imbalance_settlement",
    }


def test_candidates_are_not_registered() -> None:
    for candidate in ("ote.ida", "ceps.crossborder_flows", "ceps.generation"):
        assert dataset(candidate) is None


def test_imbalance_settlement_contract() -> None:
    """Admitted 2026-09-23 (docs/admissions/ote_imbalance_settlement.md); no adapter yet."""
    c = dataset("ote.imbalance_settlement")
    assert c is not None
    assert c.source_id == "ote"
    assert c.identity_key == ("bidding_zone", "delivery_start_utc", "resolution", "version")
    assert dict(c.fixed_dimensions) == {"bidding_zone": "CZ"}
    assert c.manifest_dimensions() == ("bidding_zone",)
    assert c.version_in_identity is True
    assert c.resolutions == ("PT15M", "PT60M")
    assert set(c.metrics) == {"system_imbalance", "imbalance_price", "counter_imbalance_price"}
    assert c.metrics["system_imbalance"].unit == "MWh"
    assert c.metrics["imbalance_price"].unit == "CZK/MWh"
    assert all(m.sign == "negative_allowed" for m in c.metrics.values())
    assert all(m.owner_transport == "soap" for m in c.metrics.values())


def test_idm_continuous_contract() -> None:
    c = dataset("ote.idm_continuous")
    assert isinstance(c, DatasetContract)
    assert c.source_id == "ote"
    assert c.identity_key == ("bidding_zone", "delivery_start_utc", "resolution")
    assert dict(c.fixed_dimensions) == {"bidding_zone": "CZ"}
    assert set(c.metrics) == {
        "price_vwap",
        "volume_total",
        "volume_buy",
        "volume_sell",
        "price_min",
        "price_max",
        "price_last",
    }
    assert c.metrics["price_vwap"].owner_transport == "soap"
    assert c.metrics["volume_total"].owner_transport == "soap"
    assert c.metrics["price_last"].owner_transport == "xlsx"
    assert c.metrics["price_vwap"].sign == "negative_allowed"
    assert c.metrics["volume_total"].sign == "non_negative"
    assert c.resolutions == ("PT15M", "PT60M")


def test_dam_contract() -> None:
    c = dataset("ote.dam")
    assert c is not None
    assert c.identity_key == ("bidding_zone", "delivery_start_utc", "resolution")
    assert set(c.metrics) == {"price", "price_hourly", "volume_total", "emergency_state"}
    assert c.metrics["emergency_state"].unit == "1"


def test_ceps_load_contract() -> None:
    c = dataset("ceps.load")
    assert c is not None
    assert c.source_id == "ceps"
    assert c.identity_key == (
        "area",
        "delivery_start_utc",
        "resolution",
        "aggregation_function",
        "version",
    )
    assert dict(c.fixed_dimensions) == {"area": "CZ"}
    assert c.manifest_dimensions() == ("area", "aggregation_function")
    assert c.version_in_identity is True
    assert set(c.metrics) == {"load_incl_pumping", "load"}
    assert c.metrics["load"].unit == "MW"
    assert c.metrics["load"].sign == "non_negative_expected"


def test_every_metric_has_registry_semantics() -> None:
    for c in DATASETS.values():
        assert SEMVER.match(c.contract_version)
        assert c.identity_key[1:3] == ("delivery_start_utc", "resolution")
        for name, m in c.metrics.items():
            assert m.name == name
            assert m.unit in {"EUR/MWh", "CZK/MWh", "MWh", "MW", "1"}
            assert m.null_meaning
            currency = {"EUR/MWh": "EUR", "CZK/MWh": "CZK"}.get(m.unit)
            assert m.currency == currency
