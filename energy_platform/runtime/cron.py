"""A five-field cron evaluator (ADR-031 §1): minute hour day-of-month month day-of-week.

Supports ``*``, ``n``, ``a-b``, ``*/s``, ``a-b/s`` and comma lists; day-of-week 0 and 7 are
Sunday. As in Vixie cron, when both day fields are restricted an instant matches if either
does. Instants are evaluated minute by minute in the manifest's timezone, so a ``*/15`` cadence
yields 92 or 100 instants on a DST day exactly like the delivery intervals do.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _field(text: str, lo: int, hi: int) -> frozenset[int]:
    values: set[int] = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step < 1:
                raise ValueError(f"cron step must be >= 1: {text!r}")
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a_text, b_text = part.split("-", 1)
            a, b = int(a_text), int(b_text)
        else:
            a = b = int(part)
            if step != 1:
                b = hi
        if not (lo <= a <= b <= hi):
            raise ValueError(f"cron field {text!r} outside {lo}..{hi}")
        values.update(range(a, b + 1, step))
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class CronExpression:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    day_restricted: bool
    weekday_restricted: bool

    @classmethod
    def parse(cls, text: str) -> CronExpression:
        fields = text.split()
        if len(fields) != 5:
            raise ValueError(f"cron needs five fields: {text!r}")
        parsed = [_field(f, lo, hi) for f, (lo, hi) in zip(fields, _RANGES, strict=True)]
        weekdays = frozenset(0 if d == 7 else d for d in parsed[4])
        return cls(
            minutes=parsed[0],
            hours=parsed[1],
            days=parsed[2],
            months=parsed[3],
            weekdays=weekdays,
            day_restricted=fields[2] != "*",
            weekday_restricted=fields[4] != "*",
        )

    def matches(self, local: datetime) -> bool:
        if local.minute not in self.minutes or local.hour not in self.hours:
            return False
        if local.month not in self.months:
            return False
        day_ok = local.day in self.days
        weekday_ok = (local.isoweekday() % 7) in self.weekdays  # Sunday = 0
        if self.day_restricted and self.weekday_restricted:
            return day_ok or weekday_ok
        return day_ok and weekday_ok


def cron_instants(
    expression: str, timezone: str, start: datetime, end: datetime
) -> Iterator[datetime]:
    """Firing instants with ``start < t <= end``, as aware UTC datetimes, minute resolution."""
    cron = CronExpression.parse(expression)
    zone = ZoneInfo(timezone)
    t = start.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
    stop = end.astimezone(UTC)
    while t <= stop:
        if cron.matches(t.astimezone(zone)):
            yield t
        t += timedelta(minutes=1)


def cadence_of(expression: str, timezone: str, reference: datetime) -> timedelta:
    """Smallest gap between consecutive instants in the day around ``reference``."""
    instants = list(
        cron_instants(
            expression, timezone, reference - timedelta(days=1), reference + timedelta(days=1)
        )
    )
    gaps = [b - a for a, b in pairwise(instants)]
    return min(gaps) if gaps else timedelta(days=1)
