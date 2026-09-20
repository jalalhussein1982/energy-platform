"""The gap detector (ADR-031; ADR-024 §5): expected instants versus Bronze and the ledger.

Per expected instant older than the tolerance (2 x cadence):

* a capture-log entry exists and the run is ``processed`` → nothing;
* an entry exists and the run is not ``processed`` → ``unprocessed_capture`` (the row is
  reconciled if missing; the next ``process`` claims it);
* no entry, inside ``history.max_age`` → ``missing_capture`` (a run in that state, which
  ``backfill`` fetches);
* no entry, outside ``history.max_age`` → ``unrecoverable`` plus an ``error`` quality event.

``history.max_age: none`` means the source serves no history at all: every missing period is
unrecoverable (the conservative reading; ADR-024 rejected silent refetching).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from energy_platform.mapping import QualityEvent
from energy_platform.runtime.context import Runtime
from energy_platform.runtime.cron import cadence_of, cron_instants

GapKind = Literal["pending", "unprocessed_capture", "missing_capture", "unrecoverable"]

_MAX_AGE = re.compile(
    r"^P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?)?$"
)


@dataclass(frozen=True, slots=True)
class Gap:
    scheduled_for: datetime
    kind: GapKind
    action: str


def max_age_cutoff(now: datetime, max_age: str, tz: str) -> datetime | None:
    """Oldest instant the source still serves; ``None`` for ``none`` (no history at all).

    Calendar arithmetic (P2-D12): years, months, weeks and days step the source's local
    calendar (day clamped, wall clock kept across DST); hours and minutes are exact.
    """
    if max_age == "none":
        return None
    m = _MAX_AGE.match(max_age)
    if not m or max_age in {"P", "PT"}:
        raise ValueError(f"history.max_age is not an ISO 8601 duration: {max_age!r}")
    g = {k: int(v) for k, v in m.groupdict().items() if v is not None}
    local = now.astimezone(ZoneInfo(tz))
    months_back = g.get("years", 0) * 12 + g.get("months", 0)
    year, month = local.year, local.month - months_back
    while month < 1:
        month += 12
        year -= 1
    day = min(local.day, _days_in_month(year, month))
    shifted = local.replace(year=year, month=month, day=day)
    shifted -= timedelta(weeks=g.get("weeks", 0), days=g.get("days", 0))  # wall clock
    exact = timedelta(hours=g.get("hours", 0), minutes=g.get("minutes", 0))
    return shifted.astimezone(UTC) - exact


def _days_in_month(year: int, month: int) -> int:
    nxt = datetime(year + (month // 12), month % 12 + 1, 1, tzinfo=ZoneInfo("UTC"))
    return (nxt - timedelta(days=1)).day


def detect_gaps(
    rt: Runtime, *, lookback: timedelta | None = None, now: datetime | None = None
) -> tuple[Gap, ...]:
    now = now or rt.clock()
    lookback = lookback or rt.reconcile_window
    cadence = rt.manifest.cadence
    tolerance = 2 * cadence_of(cadence.cron, cadence.timezone, now)
    cutoff = max_age_cutoff(now, rt.manifest.history.max_age, rt.timezone)
    start = now - lookback
    entries = {}
    for e in rt.bronze.log.list(rt.target_id, since=start):
        entries[e.scheduled_for] = e
    runs = {r.scheduled_for: r for r in rt.store.runs(rt.target_id, since=start)}
    gaps: list[Gap] = []
    for t in cron_instants(cadence.cron, cadence.timezone, start, now):
        if now - t < tolerance:
            gaps.append(Gap(t, "pending", "inside tolerance; nothing to do"))
            continue
        entry = entries.get(t)
        run = runs.get(t)
        if entry is not None:
            if run is None or run.capture_id is None:
                run = rt.store.ensure_run(
                    rt.target_id,
                    t,
                    state="captured",
                    origin="reconciled",
                    capture_id=entry.capture_id,
                    now=now,
                )
            if run.state != "processed":
                gaps.append(Gap(t, "unprocessed_capture", "replay: the next process run claims it"))
            continue
        recoverable = cutoff is not None and t >= cutoff
        if recoverable:
            if run is None:
                rt.store.ensure_run(
                    rt.target_id, t, state="missing_capture", origin="backfill", now=now
                )
            elif run.state in {"scheduled", "failed"}:
                rt.store.set_state(run.id, "missing_capture", now=now)
            gaps.append(Gap(t, "missing_capture", "backfill: inside history.max_age"))
            continue
        if run is None:
            rt.store.ensure_run(rt.target_id, t, state="unrecoverable", origin="backfill", now=now)
            _alert(rt, t, now)
        elif run.state != "unrecoverable":
            rt.store.set_state(run.id, "unrecoverable", now=now)
            _alert(rt, t, now)
        gaps.append(Gap(t, "unrecoverable", "alert: outside history.max_age, never captured"))
    return tuple(gaps)


def _alert(rt: Runtime, t: datetime, now: datetime) -> None:
    rt.store.add_events(
        rt.target_id,
        [
            QualityEvent(
                "unrecoverable_gap",
                "error",
                f"{t:%Y-%m-%dT%H:%MZ}: never captured and outside history.max_age "
                f"{rt.manifest.history.max_age}",
            )
        ],
        run_attempt_id=None,
        now=now,
    )
