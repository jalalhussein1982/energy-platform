"""Dataset registry seeded from 01 §6.3 / §9 (ADR-022)."""

from __future__ import annotations

import re

from energy_platform.contracts.registry import DATASETS, DatasetContract, dataset

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_only_committed_datasets_are_registered() -> None:
    assert set(DATASETS) == {"ote.idm_continuous", "ote.dam", "ceps.load"}


def test_candidates_are_not_registered() -> None:
    for candidate in ("ote.imbalance_settlement", "ote.ida", "ceps.crossborder_flows"):
        assert dataset(candidate) is None


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
            assert m.unit in {"EUR/MWh", "MWh", "MW", "1"}
            assert m.null_meaning
            if m.unit == "EUR/MWh":
                assert m.currency == "EUR"
            else:
                assert m.currency is None
