"""``freshness``: the ADR-037 / ADR-012 SLI, computed from the calendar, Silver and the ledger.

Per target the partition is a delivery day (or hour, ``DatasetContract.partition``) in the source
timezone. ``expected_periods`` comes from the DST-aware calendar (92/96/100);
``observed_periods`` counts distinct delivery starts the owning transport has in the current view
for the partition; ``expected_by`` is the last cadence instant inside the partition plus the ADR-031
tolerance (2 x cadence). Status, in this order: ``complete`` (observed >= expected), ``pending``
(before the partition's first cadence instant), ``late`` (past ``expected_by``), else ``partial``.

Which partition the row reports: the current one, unless it is not yet complete **and** the
previous partition is late **and** the platform was collecting during it (at least one capture-log
entry with ``scheduled_for`` inside it) — a day that ended incomplete stays visible as ``late``
after midnight instead of vanishing behind a fresh ``partial`` day (01 §5), while the day before a
deployment is a gap-detector matter, not a freshness one.

``source_unavailable`` is true when the newest attempt in the lookback failed in the fetch layer;
``pipeline_failed`` when it failed anywhere after Bronze. A ČEPS outage at 03:00 is not our
incident; a decode failure is (ADR-012). ``last_capture_outcome`` is the newest capture or
backfill attempt's outcome, whatever ran after it.

Known weakness (ADR-037): a day-ahead source (E1) is expected per the partition's own cadence
instants, so its lateness is detected up to a day late; a manifest-level override is the fix.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from energy_platform.contracts.intervals import local_day_intervals, parse_duration
from energy_platform.contracts.registry import dataset
from energy_platform.runtime.context import Runtime, delivery_day_for
from energy_platform.runtime.cron import cadence_of, cron_instants
from energy_platform.store import Freshness, FreshnessStatus, RunAttempt

FETCH_FAILURES = frozenset({"source_unavailable"})
PIPELINE_FAILURES = frozenset({"failed", "quarantined", "lost_lease"})
_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class PartitionStatus:
    start: datetime
    end: datetime
    expected_periods: int
    observed_periods: int
    expected_by: datetime
    status: FreshnessStatus


def _finest_resolution(resolutions: tuple[str, ...]) -> str:
    return min(resolutions, key=parse_duration)


def partition_bounds(
    rt: Runtime, now: datetime, *, back: int = 0
) -> tuple[datetime, datetime, int]:
    """``(start, end, expected_periods)`` of the partition containing ``now``, or the one
    ``back`` partitions earlier."""
    contract = dataset(rt.manifest.contract.dataset_id)
    if contract is None:
        raise ValueError(f"{rt.manifest.contract.dataset_id!r} is not registered")
    resolution = _finest_resolution(contract.resolutions)
    if contract.partition == "hour":
        local = now.astimezone(ZoneInfo(rt.timezone)).replace(minute=0, second=0, microsecond=0)
        start = local.astimezone(UTC) - timedelta(hours=back)
        end = start + timedelta(hours=1)
        return start, end, int(timedelta(hours=1) / parse_duration(resolution))
    day = delivery_day_for(now, rt.timezone) - timedelta(days=back)
    intervals = local_day_intervals(day, resolution)
    return intervals[0].start, intervals[-1].end, len(intervals)


def classify_partition(rt: Runtime, now: datetime, *, back: int = 0) -> PartitionStatus:
    cadence = rt.manifest.cadence
    start, end, expected = partition_bounds(rt, now, back=back)
    instants = list(cron_instants(cadence.cron, cadence.timezone, start - _MINUTE, end - _MINUTE))
    tolerance = 2 * cadence_of(cadence.cron, cadence.timezone, now)
    first_instant = instants[0] if instants else start
    expected_by = (instants[-1] if instants else end) + tolerance
    observed = rt.store.count_periods(
        rt.manifest.contract.dataset_id,
        start,
        end,
        transport=rt.manifest.contract.source_transport,
    )
    status: FreshnessStatus
    if observed >= expected:
        status = "complete"
    elif now < first_instant:
        status = "pending"
    elif now > expected_by:
        status = "late"
    else:
        status = "partial"
    return PartitionStatus(start, end, expected, observed, expected_by, status)


def _newest_attempts(rt: Runtime, since: datetime) -> tuple[RunAttempt | None, RunAttempt | None]:
    """``(newest attempt of any kind, newest capture/backfill attempt)`` in the window."""
    newest: RunAttempt | None = None
    newest_capture: RunAttempt | None = None
    for run in rt.store.runs(rt.target_id, since=since):
        for attempt in rt.store.attempts(run.id):
            key = (attempt.started_at, attempt.id)
            if newest is None or key > (newest.started_at, newest.id):
                newest = attempt
            if attempt.kind in {"capture", "backfill"} and (
                newest_capture is None or key > (newest_capture.started_at, newest_capture.id)
            ):
                newest_capture = attempt
    return newest, newest_capture


def _stale_streak(rt: Runtime, since: datetime) -> int:
    streak = 0
    for entry in reversed(rt.bronze.log.list(rt.target_id, since=since)):
        if entry.content_changed:
            break
        streak += 1
    return streak


def compute_freshness(rt: Runtime, *, now: datetime | None = None) -> Freshness:
    now = now or rt.clock()
    chosen = classify_partition(rt, now)
    if chosen.status != "complete":
        previous = classify_partition(rt, now, back=1)
        collected_then = rt.bronze.log.list(rt.target_id, since=previous.start, until=previous.end)
        if previous.status == "late" and collected_then:
            chosen = previous
    transport = rt.manifest.contract.source_transport
    lookback = now - rt.reconcile_window
    newest, newest_capture = _newest_attempts(rt, lookback)
    last_capture = rt.bronze.log.latest(rt.target_id)
    outcome = newest.outcome if newest is not None else None
    return Freshness(
        target_id=rt.target_id,
        computed_at=now,
        partition_start=chosen.start,
        partition_end=chosen.end,
        expected_by=chosen.expected_by,
        status=chosen.status,
        observed_periods=chosen.observed_periods,
        expected_periods=chosen.expected_periods,
        newest_delivery_start=rt.store.newest_delivery_start(
            rt.manifest.contract.dataset_id, transport=transport
        ),
        last_capture_at=last_capture.fetched_at if last_capture is not None else None,
        last_capture_outcome=newest_capture.outcome if newest_capture is not None else None,
        stale_fetch_streak=_stale_streak(rt, lookback),
        source_unavailable=outcome in FETCH_FAILURES,
        pipeline_failed=outcome in PIPELINE_FAILURES,
    )


def record_freshness(rt: Runtime, *, now: datetime | None = None) -> Freshness:
    """Compute and upsert the target's row (what the gap-detector CronJob runs)."""
    row = compute_freshness(rt, now=now)
    rt.store.upsert_freshness(row)
    return row
