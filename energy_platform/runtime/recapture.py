"""``recapture``: the correction re-poll of ADR-033 §3.

For each of the previous ``days`` delivery days (in the source timezone), the **last run** of
that day is captured again with ``force=True``: a new attempt on the same
``(target_id, scheduled_for)``, no new identity. Bronze marks the attempt ``content_changed``;
only a changed payload lowers the run to ``captured`` (P5-D6, in ``capture``) so the next
``process`` claims it. A day with no run is reported and skipped — there is nothing to re-poll.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from energy_platform.runtime.capture import CaptureReport, capture
from energy_platform.runtime.context import Runtime, delivery_day_bounds, delivery_day_for


@dataclass(frozen=True, slots=True)
class RecaptureReport:
    delivery_day: date
    scheduled_for: datetime | None
    capture: CaptureReport | None
    """``None`` when the day had no run to re-capture."""

    @property
    def skipped(self) -> bool:
        return self.capture is None


def last_run_of_day(rt: Runtime, day: date) -> datetime | None:
    """The newest ``scheduled_for`` in the capture log whose delivery day is ``day``."""
    since, until = delivery_day_bounds(day, rt.timezone)
    newest: datetime | None = None
    for entry in rt.bronze.log.list(rt.target_id, since=since, until=until):
        if delivery_day_for(entry.scheduled_for, rt.timezone) != day:
            continue
        if newest is None or entry.scheduled_for > newest:
            newest = entry.scheduled_for
    return newest


def recapture(
    rt: Runtime, *, days: int, now: datetime | None = None
) -> tuple[RecaptureReport, ...]:
    if days < 1:
        raise ValueError("days must be >= 1")
    now = now or rt.clock()
    today = delivery_day_for(now, rt.timezone)
    reports: list[RecaptureReport] = []
    for back in range(1, days + 1):
        day = today - timedelta(days=back)
        scheduled_for = last_run_of_day(rt, day)
        if scheduled_for is None:
            reports.append(RecaptureReport(day, None, None))
            continue
        reports.append(RecaptureReport(day, scheduled_for, capture(rt, scheduled_for, force=True)))
    return tuple(reports)
