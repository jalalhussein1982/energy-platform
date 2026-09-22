"""ADR-037 freshness: the 01 §5 states, DST-aware expectations, hour partitions, and the
source_unavailable / pipeline_failed split, on memory backends."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from energy_platform.contracts.manifest import Manifest
from energy_platform.fetch import Fetcher, FixtureTransport
from energy_platform.runtime import (
    capture,
    compute_freshness,
    partition_bounds,
    process,
    record_freshness,
)
from energy_platform.store import MemoryStore
from tests.runtime.harness import DAY, SCHEDULED, T1, T2, T3, Clock, runtime
from tests.synthetic import ote_im_price_period_response

PRAGUE = ZoneInfo("Europe/Prague")


def local(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=PRAGUE).astimezone(UTC)


def with_cron(manifest: Manifest, cron: str) -> Manifest:
    return manifest.model_copy(
        update={"cadence": manifest.cadence.model_copy(update={"cron": cron})}
    )


def test_complete_day_after_capture_and_process() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, clock=clock)
    capture(rt, SCHEDULED)
    process(rt)
    clock.now = local("2026-09-18T10:00")
    f = compute_freshness(rt)
    assert f.status == "complete" and f.observed_periods == f.expected_periods == 96
    assert f.partition_start == local("2026-09-18T00:00")
    assert f.partition_end == local("2026-09-19T00:00")
    assert f.expected_by == local("2026-09-18T23:45") + timedelta(minutes=30)
    assert f.newest_delivery_start == local("2026-09-18T23:45")
    assert f.age == clock.now - local("2026-09-18T23:45")
    assert f.last_capture_outcome == "ok" and f.last_capture_at is not None
    assert not f.source_unavailable and not f.pipeline_failed and f.stale_fetch_streak == 0


def test_partial_then_late_when_the_day_ends_incomplete() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rows = [(i, f"{100 + i}.00", "1.000") for i in range(1, 9)]
    rt = runtime(T1, payload=ote_im_price_period_response(DAY, rows), clock=clock)
    capture(rt, SCHEDULED)
    process(rt)
    clock.now = local("2026-09-18T03:00")
    assert compute_freshness(rt).status == "partial"
    assert compute_freshness(rt).observed_periods == 8
    clock.now = local("2026-09-19T00:14")  # 23:45 + 30 min tolerance = 00:15 next day
    assert compute_freshness(rt).status == "partial"  # the new day, still inside tolerance
    clock.now = local("2026-09-19T00:16")
    late = compute_freshness(rt)  # yesterday stays visible as late, not hidden by a fresh day
    assert late.status == "late" and late.observed_periods == 8
    assert late.partition_start == local("2026-09-18T00:00")


def test_pending_before_the_first_cadence_instant_of_the_partition() -> None:
    day_ahead = with_cron(T1, "0 12-23 * * *")
    rt = runtime(day_ahead, clock=Clock(local("2026-09-18T06:00")))
    f = compute_freshness(rt)
    assert f.status == "pending" and f.observed_periods == 0
    assert f.expected_by == local("2026-09-18T23:00") + timedelta(hours=2)
    assert f.newest_delivery_start is None and f.age is None


@pytest.mark.parametrize(
    ("day", "n"), [("2026-03-29", 92), ("2025-10-26", 100), ("2026-09-18", 96)]
)
def test_expected_periods_follow_the_dst_calendar(day: str, n: int) -> None:
    rt = runtime(T1, clock=Clock(local(f"{day}T12:00")))
    start, end, expected = partition_bounds(rt, local(f"{day}T12:00"))
    assert expected == n
    assert (end - start) == timedelta(hours=24 + (0 if n == 96 else (1 if n == 100 else -1)))


def test_hour_partition_for_ceps_load() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T3, clock=clock)
    capture(rt, SCHEDULED)
    process(rt)
    clock.now = local("2026-09-18T14:20")
    f = compute_freshness(rt)
    assert f.partition_start == local("2026-09-18T14:00")
    assert f.partition_end == local("2026-09-18T15:00")
    assert f.expected_periods == 4 and f.observed_periods == 4 and f.status == "complete"
    clock.now = local("2026-09-19T13:08")  # next day: a poll during the 13:00 hour, no rows
    capture(rt, local("2026-09-19T13:07"))
    clock.now = local("2026-09-19T14:20")
    late = compute_freshness(rt)  # the 13:00 hour was collected and is still empty → late
    assert late.status == "late" and late.partition_start == local("2026-09-19T13:00")
    fresh = runtime(T3, clock=Clock(local("2026-09-19T14:20")))
    assert compute_freshness(fresh).status == "partial"  # never collected before: not late


def test_source_unavailable_is_the_sources_incident() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))

    def down(manifest: Manifest) -> Fetcher:
        return Fetcher(
            allowed_hosts=manifest.allowed_hosts,
            allow_insecure=manifest.allow_insecure,
            transport=FixtureTransport(b"", status=503),
            offline=True,
            sleep=lambda _: None,
        )

    rt = replace(runtime(T1, clock=clock), fetcher_factory=down)
    report = capture(rt, SCHEDULED)
    assert report.outcome == "source_unavailable"
    f = compute_freshness(rt)
    assert f.source_unavailable and not f.pipeline_failed
    assert f.last_capture_outcome == "source_unavailable" and f.last_capture_at is None


def test_pipeline_failed_is_ours() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, payload=b"<this is not the document", clock=clock)
    assert capture(rt, SCHEDULED).outcome == "ok"
    assert process(rt)[0].outcome in {"failed", "quarantined"}  # after Bronze: ours
    f = compute_freshness(rt)
    assert f.pipeline_failed and not f.source_unavailable
    assert f.last_capture_outcome == "ok"  # the capture itself was fine (ADR-004)


def test_stale_fetch_streak_counts_unchanged_captures() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, clock=clock)
    for k in range(3):
        when = SCHEDULED + timedelta(minutes=15 * k)
        clock.now = when + timedelta(minutes=1)
        capture(rt, when)
    assert compute_freshness(rt).stale_fetch_streak == 2


def test_record_freshness_upserts_one_row_per_target() -> None:
    rt = runtime(T1, clock=Clock(local("2026-09-18T10:00")))
    first = record_freshness(rt)
    rt.clock.advance(timedelta(minutes=15))  # type: ignore[attr-defined]
    second = record_freshness(rt)
    rows = rt.store.freshness_rows()
    assert len(rows) == 1 and rows[0] == second and second.computed_at > first.computed_at


def test_partition_day_is_the_source_civil_day() -> None:
    rt = runtime(T1)
    start, end, _ = partition_bounds(rt, datetime(2026, 9, 17, 22, 30, tzinfo=UTC))
    assert start == local("2026-09-18T00:00") and end == local("2026-09-19T00:00")
    assert date(2026, 9, 18) == start.astimezone(PRAGUE).date()


def test_a_targets_periods_are_its_own_even_when_another_transport_wins_the_view() -> None:
    """T1 (soap) and T2 (xlsx) deliver the same dataset; the current view keeps one row per
    identity (ADR-023 §3) but freshness is per target: T1 counts what T1 delivered."""
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    store = MemoryStore()
    t1 = runtime(T1, store=store, clock=clock)
    capture(t1, SCHEDULED)
    process(t1)
    clock.now = SCHEDULED + timedelta(minutes=16)
    t2 = runtime(T2, store=store, clock=clock)
    capture(t2, SCHEDULED + timedelta(minutes=15))
    process(t2)
    clock.now = local("2026-09-18T10:00")
    assert compute_freshness(t1).observed_periods == 96
    assert compute_freshness(t2).observed_periods == 96


def test_null_values_are_not_observed_periods() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rows = [(i, f"{100 + i}.00", "1.000") for i in range(1, 9)] + [
        (i, None, None) for i in range(9, 97)
    ]
    rt = runtime(T1, payload=ote_im_price_period_response(DAY, rows), clock=clock)
    capture(rt, SCHEDULED)
    process(rt)
    clock.now = local("2026-09-18T03:00")
    f = compute_freshness(rt)
    assert f.observed_periods == 8 and f.status == "partial"
    assert f.newest_delivery_start == local("2026-09-18T01:45")
    assert f.age is not None and f.age > timedelta(0)
