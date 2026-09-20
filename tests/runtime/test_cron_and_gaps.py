"""Cron evaluation (ADR-031 §1), tolerance (§2), history.max_age arithmetic (P2-D12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from energy_platform.contracts.intervals import local_day_intervals
from energy_platform.runtime import CronExpression, cron_instants, max_age_cutoff
from energy_platform.runtime.cron import cadence_of

PRAGUE = "Europe/Prague"


def local(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(PRAGUE))


def test_every_15_minutes_over_an_ordinary_day() -> None:
    start, end = local("2026-09-17T23:59"), local("2026-09-18T23:59")
    instants = list(cron_instants("*/15 * * * *", PRAGUE, start, end))
    assert len(instants) == 96
    assert instants[0] == local("2026-09-18T00:00").astimezone(UTC)
    assert all(t.tzinfo is UTC for t in instants)


@pytest.mark.parametrize(("day", "n"), [("2026-03-29", 92), ("2025-10-26", 100)])
def test_dst_days_yield_92_and_100_instants_like_the_intervals(day: str, n: int) -> None:
    start = local(f"{day}T00:00") - timedelta(minutes=1)
    end = local(f"{day}T00:00") + timedelta(days=1) - timedelta(minutes=1)
    instants = list(cron_instants("*/15 * * * *", PRAGUE, start, end))
    assert len(instants) == n
    expected = [iv.start for iv in local_day_intervals(datetime.fromisoformat(day).date(), "PT15M")]
    assert instants == expected


def test_lists_ranges_steps_and_weekday_semantics() -> None:
    c = CronExpression.parse("0 12,18 1-7 * 1")  # noon and 18:00 on the 1st..7th OR every Monday
    assert c.matches(local("2026-09-07T12:00"))  # Monday the 7th
    assert c.matches(local("2026-09-14T18:00"))  # Monday the 14th (weekday matches)
    assert c.matches(local("2026-09-03T12:00"))  # Thursday the 3rd (day matches)
    assert not c.matches(local("2026-09-10T12:00"))  # Thursday the 10th
    assert not c.matches(local("2026-09-07T13:00"))
    hourly = CronExpression.parse("30 */6 * * 0,7")
    assert hourly.matches(local("2026-09-20T06:30"))  # Sunday
    assert not hourly.matches(local("2026-09-21T06:30"))


@pytest.mark.parametrize(
    "bad", ["* * * *", "60 * * * *", "*/0 * * * *", "0 25 * * *", "0 0 32 * *"]
)
def test_invalid_expressions_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        CronExpression.parse(bad)


def test_cadence_is_the_smallest_gap() -> None:
    now = datetime(2026, 9, 18, 12, tzinfo=UTC)
    assert cadence_of("*/15 * * * *", PRAGUE, now) == timedelta(minutes=15)
    assert cadence_of("0 * * * *", PRAGUE, now) == timedelta(hours=1)
    assert cadence_of("0 12 * * *", PRAGUE, now) == timedelta(days=1)


def test_max_age_calendar_arithmetic_and_none() -> None:
    now = datetime(2026, 3, 31, 10, 0, tzinfo=UTC)  # 12:00 Prague, CEST
    assert max_age_cutoff(now, "none", PRAGUE) is None
    one_month = max_age_cutoff(now, "P1M", PRAGUE)
    assert (
        one_month is not None
        and one_month.astimezone(ZoneInfo(PRAGUE)).date().isoformat() == "2026-02-28"
    )
    two_years = max_age_cutoff(now, "P2Y", PRAGUE)
    assert (
        two_years is not None
        and two_years.astimezone(ZoneInfo(PRAGUE)).date().isoformat() == "2024-03-31"
    )
    assert max_age_cutoff(now, "PT48H", PRAGUE) == now - timedelta(hours=48)  # exact
    # days keep the local wall clock across the DST change: 12:00 CET on 2026-02-28
    assert max_age_cutoff(now, "P31D", PRAGUE) == local("2026-02-28T12:00")
    assert max_age_cutoff(now, "P1W", PRAGUE) == local("2026-03-24T12:00")
    assert max_age_cutoff(now, "P1DT1H", PRAGUE) == local("2026-03-30T12:00") - timedelta(hours=1)
    with pytest.raises(ValueError, match="ISO 8601"):
        max_age_cutoff(now, "2 years", PRAGUE)
