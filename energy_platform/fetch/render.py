"""Placeholder rendering for the declarative fetch block (04 §3.3).

Only three names exist: ``delivery_day`` (a date, so ``{delivery_day:%Y-%m-%d}`` works),
``next_delivery_day`` (the following civil day, for sources that publish day D on D-1 — ADR-033
§4) and ``scheduled_for`` (an aware datetime). Anything else is a :class:`RenderError`, never
silently left in place.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from energy_platform.contracts.intervals import SOURCE_TIMEZONE


class RenderError(ValueError):
    """A template names a placeholder the run context does not provide."""


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
        }


class _Strict(dict[str, Any]):
    def __missing__(self, key: str) -> Any:
        raise RenderError(
            f"unknown placeholder {{{key}}}; only delivery_day, next_delivery_day and "
            "scheduled_for exist"
        )


def render(template: str, ctx: FetchContext) -> str:
    """Render ``{delivery_day:%Y-%m-%d}`` / ``{scheduled_for}`` placeholders in ``template``."""
    try:
        return template.format_map(_Strict(ctx.as_mapping()))
    except (KeyError, IndexError, ValueError) as exc:
        raise RenderError(f"cannot render {template!r}: {exc}") from exc


def render_with(template: str, values: Mapping[str, str]) -> str:
    """Second stage: fill a SOAP body's ``{name}`` placeholders from already-rendered params."""
    try:
        return template.format_map(_Strict(dict(values)))
    except (KeyError, IndexError, ValueError) as exc:
        raise RenderError(f"cannot render body: {exc}") from exc
