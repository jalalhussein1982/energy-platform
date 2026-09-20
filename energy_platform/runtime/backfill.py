"""``backfill``: the fetching verb for periods with no capture (ADR-024 §5)."""

from __future__ import annotations

from energy_platform.runtime.capture import CaptureReport, capture
from energy_platform.runtime.context import Runtime


def backfill(rt: Runtime, *, limit: int | None = None) -> tuple[CaptureReport, ...]:
    """Fetch every run the gap detector marked ``missing_capture`` (within ``history.max_age``)."""
    reports: list[CaptureReport] = []
    for run in rt.store.runs(rt.target_id):
        if run.state != "missing_capture":
            continue
        if limit is not None and len(reports) >= limit:
            break
        reports.append(capture(rt, run.scheduled_for, kind="backfill"))
    return tuple(reports)
