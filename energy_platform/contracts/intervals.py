"""Delivery intervals: the valid-time side of the bitemporal observation (ADR-011, ADR-018).

Rules from ``docs/01-data-scope.md`` §7 that this module makes mechanical:

* intervals are start-inclusive, end-exclusive and stored in UTC (the ``tstzrange`` form);
* conversion goes **period index → local interval → UTC**, never by attaching a timezone to an
  ambiguous wall-clock label (the autumn day repeats ``02:00``; the spring day skips it);
* the number of intervals in a local day is computed from the calendar (92 / 96 / 100 for
  ``PT15M``), never hard-coded.

Nothing here does I/O; a target parser may import it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

SOURCE_TIMEZONE = "Europe/Prague"
"""Civil time of every committed source (01 §7)."""

IntervalLabel = Literal["start", "end"]
"""Which edge of the interval a source timestamp names (02 ADR-011: never implicit)."""

_DURATION = re.compile(r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?)?$")


def parse_duration(text: str) -> timedelta:
    """Parse the ISO 8601 duration subset a source can declare (01 §6.2): PnD, PTnH, PTnM.

    Months and years are rejected on purpose: they are not fixed lengths. Zero is rejected: an
    interval must be non-empty.
    """
    m = _DURATION.match(text)
    if not m or text in {"P", "PT"}:
        raise ValueError(f"unsupported ISO 8601 duration {text!r} (expected PnD / PTnH / PTnM)")
    td = timedelta(
        days=int(m.group("days") or 0),
        hours=int(m.group("hours") or 0),
        minutes=int(m.group("minutes") or 0),
    )
    if td <= timedelta(0):
        raise ValueError(f"duration must be positive: {text!r}")
    return td


def _require_aware(value: datetime, what: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware (ADR-014)")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DeliveryInterval:
    """``[start, end)`` in UTC. Equivalent to a Postgres ``tstzrange`` with ``[)`` bounds."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = _require_aware(self.start, "delivery interval start")
        end = _require_aware(self.end, "delivery interval end")
        if not start < end:
            raise ValueError("delivery interval needs start < end")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def _local_midnight(day: date, tz: str) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(tz)).astimezone(UTC)


def local_day_intervals(
    local_date: date, resolution: str, tz: str = SOURCE_TIMEZONE
) -> tuple[DeliveryInterval, ...]:
    """Every interval of ``resolution`` in the civil day ``local_date`` of zone ``tz``, in UTC.

    The day runs from local midnight to the next local midnight; both are unambiguous instants,
    so the count follows from the calendar: 92 quarter-hours on the spring transition day, 100 on
    the autumn one, 96 otherwise.
    """
    step = parse_duration(resolution)
    start = _local_midnight(local_date, tz)
    end = _local_midnight(local_date + timedelta(days=1), tz)
    span = end - start
    if span % step:
        raise ValueError(f"{resolution} does not tile the local day {local_date} in {tz}")
    count = span // step
    return tuple(DeliveryInterval(start + i * step, start + (i + 1) * step) for i in range(count))


def interval_for_index(
    local_date: date, period_index: int, resolution: str, tz: str = SOURCE_TIMEZONE
) -> DeliveryInterval:
    """Map a 1-based source period index (OTE ``PeriodIndex`` / XLSX ``Period``) to its interval."""
    intervals = local_day_intervals(local_date, resolution, tz)
    if not 1 <= period_index <= len(intervals):
        raise IndexError(
            f"period_index {period_index} outside 1..{len(intervals)} "
            f"for {local_date} @ {resolution}"
        )
    return intervals[period_index - 1]


def interval_from_timestamp(
    ts: datetime, resolution: str, label: IntervalLabel
) -> DeliveryInterval:
    """Interval named by an offset-aware source timestamp that labels its ``start`` or ``end``."""
    instant = _require_aware(ts, "source timestamp")
    step = parse_duration(resolution)
    if label == "start":
        return DeliveryInterval(instant, instant + step)
    return DeliveryInterval(instant - step, instant)
