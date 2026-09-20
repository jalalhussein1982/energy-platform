"""Mapping engine: intervals, decimals, sign rules, quarantine causes, quality events."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from energy_platform.contracts.intervals import local_day_intervals
from energy_platform.contracts.manifest import Manifest, load_manifest
from energy_platform.contracts.parser import SourceRecord
from energy_platform.mapping import (
    MappingContext,
    MappingResult,
    Quarantined,
    map_records,
    partition_status,
)
from energy_platform.mapping.completeness import status_of
from energy_platform.parse import decode, generic_parser
from tests.synthetic import XLSX_HEADER, ceps_load_response, ote_im_price_period_response, ote_xlsx

EX = Path("examples/manifests")
T1 = load_manifest(EX / "ote_idm_soap.yaml")
T2 = load_manifest(EX / "ote_idm_xlsx.yaml")
T3 = load_manifest(EX / "ceps_load_soap.yaml")
HTML = load_manifest(EX / "ote_idm_html_table.yaml")
DAY = date(2026, 9, 17)
SHA = "b" * 64


def ctx(day: date = DAY, **overrides: Any) -> MappingContext:
    base: dict[str, Any] = {
        "target_id": "t",
        "scheduled_for": datetime(2026, 9, 18, 0, 15, tzinfo=UTC),
        "delivery_day": day,
        "fetched_at": datetime(2026, 9, 18, 0, 16, tzinfo=UTC),
        "raw_ref": f"bronze/blobs/{SHA[:2]}/{SHA}",
        "payload_sha256": SHA,
        "processed_at": datetime(2026, 9, 18, 0, 17, tzinfo=UTC),
        "derivation_id": "0123456789abcdef",
    }
    base.update(overrides)
    return MappingContext(**base)


def run(manifest: Manifest, payload: bytes, day: date = DAY) -> MappingResult:
    records = generic_parser(manifest).parse(decode(payload, manifest.contract.decode))
    return map_records(manifest, records, ctx(day))


def rec(**fields: Any) -> SourceRecord:
    return SourceRecord(fields=fields, locator="test")


# ------------------------------------------------------------------ T1


def test_t1_records_become_two_metric_rows_per_period_with_the_envelope() -> None:
    payload = ote_im_price_period_response(
        DAY, [(1, "170.13", "125.275"), (2, "170.21", "126.025")]
    )
    result = run(T1, payload)
    rows = result.observations
    assert len(rows) == 4
    price = next(o for o in rows if o.metric == "price_vwap" and o.period_index == 1)
    assert price.value == Decimal("170.13") and price.unit == "EUR/MWh"
    assert price.delivery_start_utc == datetime(2026, 9, 16, 22, 0, tzinfo=UTC)
    assert price.delivery_end_utc == datetime(2026, 9, 16, 22, 15, tzinfo=UTC)
    assert (price.local_date, price.resolution, price.kind) == (DAY, "PT15M", "interval")
    assert price.dimensions == {"bidding_zone": "CZ"}
    assert price.source_transport == "soap" and price.source_version is None
    assert price.source_published_at is None  # never filled from fetched_at
    assert price.raw_ref.endswith(SHA) and price.derivation_id == "0123456789abcdef"
    assert result.events == ()


def test_absent_price_is_null_never_zero() -> None:
    result = run(T1, ote_im_price_period_response(DAY, [(1, None, "125.275")]))
    price = next(o for o in result.observations if o.metric == "price_vwap")
    assert price.value is None
    volume = next(o for o in result.observations if o.metric == "volume_total")
    assert volume.value == Decimal("125.275")


def test_negative_and_zero_prices_are_kept() -> None:
    result = run(T1, ote_im_price_period_response(DAY, [(1, "-12.50", "0"), (2, "0.00", "1")]))
    values = {(o.period_index, o.metric): o.value for o in result.observations}
    assert values[(1, "price_vwap")] == Decimal("-12.50")
    assert values[(1, "volume_total")] == Decimal("0")
    assert values[(2, "price_vwap")] == Decimal("0.00")


def test_negative_volume_quarantines_the_document() -> None:
    with pytest.raises(Quarantined, match="volume_total: negative"):
        run(T1, ote_im_price_period_response(DAY, [(1, "10", "-1.000")]))


def test_unmapped_emerg_field_is_a_warning_not_a_quarantine() -> None:
    result = run(T1, ote_im_price_period_response(DAY, [(1, "1", "1")], emerg=True))
    assert [e.kind for e in result.events] == ["unknown_field"]
    assert "Emerg" in result.events[0].message and result.events[0].severity == "warning"


def test_period_index_outside_the_day_quarantines() -> None:
    with pytest.raises(Quarantined, match="period_index 97 outside"):
        run(T1, ote_im_price_period_response(DAY, [(97, "1", "1")]))


def test_hourly_native_resolution_is_preserved() -> None:
    payload = ote_im_price_period_response(
        date(2024, 6, 30), [(1, "80.5", "10")], resolution="PT60M"
    )
    o = run(T1, payload, date(2024, 6, 30)).observations[0]
    assert o.resolution == "PT60M"
    assert (
        o.delivery_end_utc - o.delivery_start_utc
        == local_day_intervals(date(2024, 6, 30), "PT60M")[0].duration
    )


def test_non_decimal_text_quarantines() -> None:
    with pytest.raises(Quarantined, match="price_vwap: not a decimal"):
        run(T1, ote_im_price_period_response(DAY, [(1, "1,234.5", "1")]))
    with pytest.raises(Quarantined, match="price_vwap"):
        run(T1, ote_im_price_period_response(DAY, [(1, "NaN", "1")]))


def test_same_period_twice_with_different_values_quarantines() -> None:
    with pytest.raises(Quarantined, match="appears twice"):
        run(T1, ote_im_price_period_response(DAY, [(1, "1", "1"), (1, "2", "1")]))
    same = run(T1, ote_im_price_period_response(DAY, [(1, "1", "1"), (1, "1", "1")]))
    assert len(same.observations) == 2


# ------------------------------------------------------------------ T2 (XLSX, DST)


@pytest.mark.parametrize(
    ("day", "n"), [(DAY, 96), (date(2026, 3, 29), 92), (date(2025, 10, 26), 100)]
)
def test_t2_days_map_completely_and_tile_the_day(day: date, n: int) -> None:
    result = run(T2, ote_xlsx(day), day)
    starts = sorted({o.delivery_start_utc for o in result.observations})
    assert len(starts) == n and len(result.observations) == 7 * n
    expected = [iv.start for iv in local_day_intervals(day, "PT15M")]
    assert starts == expected
    status = partition_status(result.observations, "PT15M", "Europe/Prague")
    assert status_of(status[0]) == "complete"
    # "Time interval" is display only (01 §3) and the manifest says so: no warning (ADR-034)
    assert result.events == ()


def test_ignore_fields_silences_only_the_listed_columns() -> None:
    header = (*XLSX_HEADER, "Note")
    result = run(T2, ote_xlsx(DAY, header=header))
    assert [e.kind for e in result.events] == ["unknown_field"]
    assert "Note" in result.events[0].message and "Time interval" not in result.events[0].message


def test_ignore_fields_on_t1_silences_emerg() -> None:
    data = T1.model_dump(mode="json")
    data["mapping"]["ignore_fields"] = ["Emerg"]
    m = Manifest.model_validate(data)
    result = run(m, ote_im_price_period_response(DAY, [(1, "1", "1")], emerg=True))
    assert result.events == () and len(result.observations) == 2


def test_t2_partial_day_is_partial() -> None:
    result = run(T2, ote_xlsx(DAY, filled=8))
    status = partition_status(result.observations, "PT15M", "Europe/Prague")
    assert status[0].message == "2026-09-17: partial 8/96"
    nulls = [o for o in result.observations if o.value is None]
    assert len(nulls) == 7 * 88


def test_t2_date_comes_from_the_run_context() -> None:
    result = run(T2, ote_xlsx(DAY), DAY)
    assert {o.local_date for o in result.observations} == {DAY}


# ------------------------------------------------------------------ T3 (timestamp, offset-aware)


def test_t3_start_label_maps_the_offset_aware_timestamp() -> None:
    result = run(T3, ceps_load_response(DAY, hours=1))
    rows = result.observations
    assert len(rows) == 8  # 4 quarter-hours x 2 metrics
    first = next(o for o in rows if o.metric == "load_incl_pumping")
    assert first.delivery_start_utc == datetime(2026, 9, 16, 22, 0, tzinfo=UTC)
    assert first.value == Decimal("6382.400") and first.unit == "MW"
    assert first.dimensions == {"area": "CZ", "aggregation_function": "AVG"}
    assert first.source_version == "RT" and first.period_index is None and first.local_date == DAY


def test_t3_end_label_shifts_the_interval_back() -> None:
    data = T3.model_dump(mode="json")
    data["mapping"]["time"]["interval_label"] = "end"
    m = Manifest.model_validate(data)
    result = run(m, ceps_load_response(DAY, hours=1))
    first = min(o.delivery_start_utc for o in result.observations)
    assert first == datetime(2026, 9, 16, 21, 45, tzinfo=UTC)


def test_t3_negative_load_is_a_warning_and_the_row_is_kept() -> None:
    ts = datetime.fromisoformat("2026-09-17T00:00:00+02:00")
    result = run(T3, ceps_load_response(DAY, [(ts, "-5.0", "6000")]))
    assert [e.kind for e in result.events] == ["negative_value"]
    assert result.events[0].metric == "load_incl_pumping"
    assert next(o.value for o in result.observations if o.metric == "load_incl_pumping") == Decimal(
        "-5.0"
    )


def test_t3_naive_timestamp_quarantines() -> None:
    naive = datetime(2026, 9, 17, 0, 0)  # noqa: DTZ001 — the point is that it has no offset
    with pytest.raises(Quarantined, match="no UTC offset"):
        run(T3, ceps_load_response(DAY, [(naive, "1", "1")]))


# ------------------------------------------------------------------ decimal comma, sign inversion


def test_decimal_comma_rule_and_dot_text_rejection() -> None:
    fields = {"Period": "1"} | {mm.source: "170,13" for mm in HTML.mapping.metrics.values()}
    result = map_records(HTML, [rec(**fields)], ctx())
    assert all(o.value == Decimal("170.13") for o in result.observations)
    bad = {"Period": "1"} | {mm.source: "170.13" for mm in HTML.mapping.metrics.values()}
    with pytest.raises(Quarantined, match="comma rule"):
        map_records(HTML, [rec(**bad)], ctx())


@given(
    st.decimals(
        allow_nan=False,
        allow_infinity=False,
        places=2,
        min_value=Decimal("-500"),
        max_value=Decimal("500"),
    )
)
def test_sign_inversion_negates_price(value: Decimal) -> None:
    data = T1.model_dump(mode="json")
    data["mapping"]["metrics"]["price_vwap"]["sign"] = "inverted"
    m = Manifest.model_validate(data)
    result = map_records(
        m,
        [rec(Date="2026-09-17", PeriodResolution="PT15M", PeriodIndex="1", Price=str(value))],
        ctx(),
    )
    price = next(o for o in result.observations if o.metric == "price_vwap")
    assert price.value == (-value if value else abs(value)) and price.sign_convention == "inverted"


def test_missing_time_field_quarantines() -> None:
    with pytest.raises(Quarantined, match="resolution is empty"):
        map_records(T1, [rec(Date="2026-09-17", PeriodIndex="1", Price="1")], ctx())
    with pytest.raises(Quarantined, match="date is not ISO"):
        map_records(T1, [rec(Date="17.09.2026", PeriodResolution="PT15M", PeriodIndex="1")], ctx())
    with pytest.raises(Quarantined, match="not an integer"):
        map_records(
            T1, [rec(Date="2026-09-17", PeriodResolution="PT15M", PeriodIndex="one")], ctx()
        )


def test_undeclared_resolution_quarantines_via_the_registry() -> None:
    with pytest.raises(Quarantined, match="resolution 'PT30M' not declared"):
        map_records(T1, [rec(Date="2026-09-17", PeriodResolution="PT30M", PeriodIndex="1")], ctx())


def test_empty_document_maps_to_no_rows_and_an_empty_partition() -> None:
    result = map_records(T1, [], ctx())
    assert result.observations == () and result.events == ()
    assert partition_status([], "PT15M", "Europe/Prague") == ()
