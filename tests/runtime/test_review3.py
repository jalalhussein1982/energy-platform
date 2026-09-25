"""Review 3 (2026-09-25, codex-astra) counterexamples as negative tests.

Each test is the reviewer's probe (``codex-review/evidence/*.py``) with its assertion turned
around: the probe asserted the defect, the test asserts the fix. R2 (the schedule's instant),
R4 (the implementation inside the derivation identity), R5 and R6 (the drill's cohort and its
value guarantee). Store-level halves that must hold on PostgreSQL live in ``tests/store``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from energy_platform.runtime import (
    backfill,
    capture,
    detect_gaps,
    instant_from_job_name,
    intended_instant,
    latest_instant,
    process,
)
from tests.runtime.harness import SCHEDULED, T1, Clock, runtime

PRAGUE = "Europe/Prague"

# ---------------------------------------------------------------------------- R2: the instant


def test_r2_a_capture_started_25_seconds_late_serves_its_tick_and_nothing_is_refetched() -> None:
    """The reviewer's ``schedule_probe.py`` inverted: the pod starts 25.69 s after its tick.
    Keyed by the schedule's instant, the capture is the tick's; the gap detector finds no
    phantom and the backfill has nothing to fetch — one Bronze entry, one source read."""
    actual_start = SCHEDULED + timedelta(seconds=25, microseconds=693263)
    clock = Clock(actual_start)
    rt = runtime(clock=clock)
    when = intended_instant(rt.manifest, actual_start)
    assert when == SCHEDULED
    assert capture(rt, when).outcome == "ok"
    assert process(rt)[0].outcome == "ok"
    clock.now = SCHEDULED + timedelta(minutes=31)
    gaps = detect_gaps(rt, lookback=timedelta(minutes=31, seconds=1))
    assert [g.kind for g in gaps if g.scheduled_for == SCHEDULED] == []
    assert all(g.kind == "pending" for g in gaps)
    assert backfill(rt, limit=1) == ()
    assert len(rt.bronze.log.list(rt.target_id)) == 1


def test_r2_the_controllers_tick_is_read_from_the_job_name() -> None:
    """A CronJob-created Job is named ``<cronjob>-<minutes since the epoch>`` of its scheduled
    time: the demo's own Job name decodes to its tick, and the tick wins over the wall clock
    even when the pod starts so late that the next tick has passed."""
    name = "energy-platform-capture-ceps-load-29838195"
    tick = instant_from_job_name(name)
    assert tick == datetime(2026, 9, 24, 23, 15, tzinfo=UTC)
    late = tick + timedelta(minutes=20, seconds=3)  # past the 23:30 tick of a */15 cadence
    assert intended_instant(T1, late, name) == tick
    assert intended_instant(T1, late, None) == tick + timedelta(minutes=15)  # the fallback


def test_r2_a_job_name_without_a_valid_tick_falls_back_to_the_newest_firing_instant() -> None:
    now = SCHEDULED + timedelta(seconds=40)
    assert instant_from_job_name("restore-drill-manual-3") is None
    assert instant_from_job_name(None) is None and instant_from_job_name("") is None
    assert intended_instant(T1, now, "restore-drill-manual-3") == SCHEDULED
    # a suffix that decodes to an instant the cadence never fires at (23:17 for */15)
    off_grid = int((SCHEDULED + timedelta(minutes=2)).timestamp()) // 60
    assert intended_instant(T1, now + timedelta(minutes=2), f"x-{off_grid}") == SCHEDULED
    # a tick from another day is not this run's identity
    stale = int((SCHEDULED - timedelta(days=2)).timestamp()) // 60
    assert intended_instant(T1, now, f"x-{stale}") == SCHEDULED
    # a tick in the future (a clock skew) is refused too
    ahead = int((SCHEDULED + timedelta(minutes=15)).timestamp()) // 60
    assert intended_instant(T1, now, f"x-{ahead}") == SCHEDULED


def test_r2_a_genuinely_missed_tick_is_still_detected() -> None:
    """The fallback never invents an older instant: the 22:15 tick had no capture, the 22:30
    pod captures 22:30, and the detector still reports 22:15 as missing."""
    clock = Clock(SCHEDULED + timedelta(minutes=15, seconds=9))
    rt = runtime(clock=clock)
    when = intended_instant(rt.manifest, clock.now)
    assert when == SCHEDULED + timedelta(minutes=15)
    assert capture(rt, when).outcome == "ok"
    process(rt)
    clock.now = SCHEDULED + timedelta(minutes=46)
    gaps = {g.scheduled_for: g.kind for g in detect_gaps(rt, lookback=timedelta(minutes=47))}
    assert gaps[SCHEDULED] == "missing_capture"
    assert SCHEDULED + timedelta(minutes=15) not in gaps  # served, processed: nothing to say


def test_r2_the_instant_follows_the_cadence_timezone_and_dst() -> None:
    """A ``15 13-16 * * *`` Prague cadence at 11:20Z is the 13:15 local tick (11:15Z); on the
    autumn change-over day the two 02:30 local instants are distinct UTC instants."""
    daily = T1.model_copy(
        update={"cadence": T1.cadence.model_copy(update={"cron": "15 13-16 * * *"})}
    )
    assert intended_instant(daily, datetime(2026, 9, 24, 11, 20, tzinfo=UTC)) == datetime(
        2026, 9, 24, 11, 15, tzinfo=UTC
    )
    # 2026-10-25: 02:31 CEST is 00:31Z, 02:31 CET an hour later is 01:31Z
    assert intended_instant(T1, datetime(2026, 10, 25, 0, 31, tzinfo=UTC)) == datetime(
        2026, 10, 25, 0, 30, tzinfo=UTC
    )
    assert intended_instant(T1, datetime(2026, 10, 25, 1, 31, tzinfo=UTC)) == datetime(
        2026, 10, 25, 1, 30, tzinfo=UTC
    )
    # a monthly cadence is found across the month boundary; a never-firing one floors now
    monthly = latest_instant("37 7 1 * *", PRAGUE, datetime(2026, 9, 24, 12, 0, tzinfo=UTC))
    assert monthly == datetime(2026, 9, 1, 5, 37, tzinfo=UTC)
    assert latest_instant("0 0 30 2 *", PRAGUE, datetime(2026, 9, 24, 12, 0, tzinfo=UTC)) is None
    never = T1.model_copy(update={"cadence": T1.cadence.model_copy(update={"cron": "0 0 30 2 *"})})
    assert intended_instant(never, datetime(2026, 9, 24, 12, 0, 7, tzinfo=UTC)) == datetime(
        2026, 9, 24, 12, 0, tzinfo=UTC
    )
