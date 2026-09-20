"""DST-safe delivery intervals (ADR-011, ADR-018, 01 §7)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from energy_platform.contracts.intervals import (
    DeliveryInterval,
    interval_for_index,
    interval_from_timestamp,
    local_day_intervals,
    parse_duration,
)

PRAGUE = ZoneInfo("Europe/Prague")


def _local_midnight_utc(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), tzinfo=PRAGUE).astimezone(UTC)


def test_spring_day_has_92_quarter_hours() -> None:
    assert len(local_day_intervals(date(2026, 3, 29), "PT15M")) == 92


def test_autumn_day_has_100_quarter_hours() -> None:
    assert len(local_day_intervals(date(2025, 10, 26), "PT15M")) == 100


def test_ordinary_day_has_96() -> None:
    assert len(local_day_intervals(date(2026, 9, 18), "PT15M")) == 96


def test_hourly_native_day_has_24() -> None:
    assert len(local_day_intervals(date(2024, 6, 30), "PT60M")) == 24


@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)))
def test_intervals_tile_the_local_day(d: date) -> None:
    ivs = local_day_intervals(d, "PT15M")
    assert ivs[0].start == _local_midnight_utc(d)
    assert ivs[-1].end == _local_midnight_utc(d + timedelta(days=1))
    assert all(a.end == b.start for a, b in pairwise(ivs))
    assert all(iv.end - iv.start == timedelta(minutes=15) for iv in ivs)
    assert len(ivs) in {92, 96, 100}
    assert all(iv.start.tzinfo is UTC for iv in ivs)


def test_autumn_index_maps_second_0200_hour_distinctly() -> None:
    ivs = local_day_intervals(date(2025, 10, 26), "PT15M")
    # index 9 = 02:00 CEST (first), index 13 = 02:00 CET (second); same wall label, distinct UTC
    assert ivs[8].start.astimezone(PRAGUE).strftime("%H:%M") == "02:00"
    assert ivs[12].start.astimezone(PRAGUE).strftime("%H:%M") == "02:00"
    assert ivs[8].start != ivs[12].start
    assert interval_for_index(date(2025, 10, 26), 9, "PT15M") == ivs[8]


def test_spring_index_bridges_the_missing_hour() -> None:
    ivs = local_day_intervals(date(2026, 3, 29), "PT15M")
    # period 8 is 01:45-02:00 CET, period 9 is 03:00-03:15 CEST: the source label is 01:45-03:00
    assert ivs[7].start.astimezone(PRAGUE).strftime("%H:%M") == "01:45"
    assert ivs[8].start.astimezone(PRAGUE).strftime("%H:%M") == "03:00"


def test_index_outside_the_day_is_rejected() -> None:
    with pytest.raises(IndexError):
        interval_for_index(date(2026, 3, 29), 93, "PT15M")
    with pytest.raises(IndexError):
        interval_for_index(date(2026, 3, 29), 0, "PT15M")


def test_start_vs_end_label() -> None:
    ts = datetime(2026, 9, 17, 0, 0, tzinfo=PRAGUE)
    as_start = interval_from_timestamp(ts, "PT15M", "start")
    as_end = interval_from_timestamp(ts, "PT15M", "end")
    assert as_start.start == ts.astimezone(UTC)
    assert as_start.end - as_start.start == timedelta(minutes=15)
    assert as_end.end == ts.astimezone(UTC)
    assert as_end.start == as_start.start - timedelta(minutes=15)


def test_offset_aware_ceps_timestamp() -> None:
    # ČEPS @date carries the local offset (01 §3 T3): "2026-09-17T00:00:00+02:00"
    ts = datetime.fromisoformat("2026-09-17T00:00:00+02:00")
    iv = interval_from_timestamp(ts, "PT15M", "start")
    assert iv.start == datetime(2026, 9, 16, 22, 0, tzinfo=UTC)


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValueError, match="aware"):
        interval_from_timestamp(datetime(2026, 1, 1), "PT15M", "start")  # noqa: DTZ001


def test_naive_interval_rejected() -> None:
    with pytest.raises(ValueError, match="aware"):
        DeliveryInterval(datetime(2026, 1, 1), datetime(2026, 1, 1, 1))  # noqa: DTZ001


def test_empty_interval_rejected() -> None:
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="start < end"):
        DeliveryInterval(t, t)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PT15M", timedelta(minutes=15)),
        ("PT60M", timedelta(minutes=60)),
        ("PT1H", timedelta(hours=1)),
        ("PT1M", timedelta(minutes=1)),
        ("P1D", timedelta(days=1)),
    ],
)
def test_parse_duration(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["15min", "PT0M", "P1M", "PT15", "", "PT-15M"])
def test_bad_duration(text: str) -> None:
    with pytest.raises(ValueError, match="duration"):
        parse_duration(text)
