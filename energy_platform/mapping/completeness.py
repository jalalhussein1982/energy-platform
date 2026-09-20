"""01 §5 completeness per delivery partition: ``partial`` / ``complete`` / ``empty``.

The expected count is computed from the calendar (96 / 92 / 100), never hard-coded. A period
counts as present when at least one metric of the document carries a non-NULL value.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from energy_platform.contracts.intervals import local_day_intervals
from energy_platform.contracts.observation import EnergyObservation
from energy_platform.mapping.quality import QualityEvent


def partition_status(
    observations: Iterable[EnergyObservation], resolution: str, tz: str
) -> tuple[QualityEvent, ...]:
    present: dict[date, set[object]] = {}
    for o in observations:
        if o.value is not None:
            present.setdefault(o.local_date, set()).add(o.delivery_start_utc)
        else:
            present.setdefault(o.local_date, set())
    events: list[QualityEvent] = []
    for day in sorted(present):
        expected = len(local_day_intervals(day, resolution, tz))
        got = len(present[day])
        status = "complete" if got >= expected else ("empty" if got == 0 else "partial")
        events.append(
            QualityEvent(
                "partition_status", "info", f"{day.isoformat()}: {status} {got}/{expected}"
            )
        )
    return tuple(events)


def status_of(event: QualityEvent) -> str:
    """The status word of a ``partition_status`` event."""
    return event.message.split(": ", 1)[1].split(" ", 1)[0]
