"""Placeholder rendering for the declarative fetch block (04 §3.3).

Five names exist: ``delivery_day`` (a date, so ``{delivery_day:%Y-%m-%d}`` works),
``next_delivery_day`` (the following civil day, for sources that publish day D on D-1 — ADR-033
§4), ``scheduled_for`` (an aware datetime), and ``month_start[k]`` / ``month_end[k]`` (the first
and last civil day of the month *k* months before the delivery day's month, 0 ≤ k ≤ 12, for
sources that settle a whole month long after it ends — ADR-033 amendment 1). Anything else, an
index outside 0…12 or a month name without its index, is a :class:`RenderError`, never silently
left in place.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from energy_platform.contracts.intervals import SOURCE_TIMEZONE
from energy_platform.contracts.templates import (
    MAX_MONTHS_BACK,
    RUN_NAMES,
    TemplateError,
    check_template,
)


class RenderError(ValueError):
    """A template names a placeholder the run context does not provide."""


@dataclass(frozen=True, slots=True)
class _MonthBack:
    """``month_start`` / ``month_end``: indexable by ``k``, never formattable on its own."""

    name: str
    day: date
    end: bool

    def __getitem__(self, k: object) -> date:
        if not isinstance(k, int) or isinstance(k, bool) or not 0 <= k <= MAX_MONTHS_BACK:
            raise RenderError(f"{self.name}[{k}]: k must be an integer 0…{MAX_MONTHS_BACK}")
        months = self.day.year * 12 + (self.day.month - 1) - k
        year, month = divmod(months, 12)
        month += 1
        return date(year, month, calendar.monthrange(year, month)[1] if self.end else 1)

    def __format__(self, spec: str) -> str:
        raise RenderError(f"{self.name} needs a month index: {{{self.name}[k]:%Y-%m-%d}}")


@dataclass(frozen=True, slots=True)
class FetchContext:
    """What one run knows before it fetches."""

    scheduled_for: datetime
    delivery_day: date

    def __post_init__(self) -> None:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled_for must be timezone-aware (ADR-014)")

    @classmethod
    def for_run(
        cls, scheduled_for: datetime, *, delivery_day: date | None = None, tz: str = SOURCE_TIMEZONE
    ) -> FetchContext:
        """Default delivery day = the source's civil date of ``scheduled_for`` (01 §7)."""
        day = delivery_day or scheduled_for.astimezone(ZoneInfo(tz)).date()
        return cls(scheduled_for=scheduled_for, delivery_day=day)

    @property
    def next_delivery_day(self) -> date:
        """The civil day after ``delivery_day`` (calendar arithmetic, no timezone involved)."""
        return self.delivery_day + timedelta(days=1)

    def as_mapping(self) -> Mapping[str, Any]:
        return {
            "delivery_day": self.delivery_day,
            "next_delivery_day": self.next_delivery_day,
            "scheduled_for": self.scheduled_for,
            "month_start": _MonthBack("month_start", self.delivery_day, end=False),
            "month_end": _MonthBack("month_end", self.delivery_day, end=True),
        }


class _Strict(dict[str, Any]):
    def __missing__(self, key: str) -> Any:
        raise RenderError(
            f"unknown placeholder {{{key}}}; only delivery_day, next_delivery_day, "
            "scheduled_for, month_start[k] and month_end[k] exist"
        )


def _check(template: str, names: frozenset[str], *, month_index: bool) -> None:
    try:
        check_template(template, names=names, month_index=month_index)
    except TemplateError as exc:
        raise RenderError(str(exc)) from exc


def render(template: str, ctx: FetchContext) -> str:
    """Render ``{delivery_day:%Y-%m-%d}`` / ``{scheduled_for}`` placeholders in ``template``."""
    _check(template, RUN_NAMES, month_index=True)
    try:
        return template.format_map(_Strict(ctx.as_mapping()))
    except RenderError:
        raise
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RenderError(f"cannot render {template!r}: {exc}") from exc


def render_with(template: str, values: Mapping[str, str]) -> str:
    """Second stage: fill a SOAP body's ``{name}`` placeholders from already-rendered params."""
    _check(template, frozenset(values), month_index=False)
    try:
        return template.format_map(_Strict(dict(values)))
    except RenderError:
        raise
    except (KeyError, IndexError, ValueError) as exc:
        raise RenderError(f"cannot render body: {exc}") from exc
