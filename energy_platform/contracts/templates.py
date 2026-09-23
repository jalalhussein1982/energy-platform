"""Fetch-template placeholders (04 §3.3; ADR-033 §4 and amendment 1).

Which names a fetch template may use and which field shapes are allowed, shared by manifest
validation (static, ``harness-check``) and :mod:`energy_platform.fetch.render` (runtime). Templates
are ``str.format`` strings, and ``str.format`` walks attributes and items of the objects it is
given: ``{x.__class__…}`` from a Python-level object reaches module globals and ``os.environ``. A
manifest must never be able to render a platform secret into a request, so only bare names are
allowed, plus ``month_start[k]`` / ``month_end[k]`` with a literal ``k`` in 0…12; no conversion
(``!r``) and no nested placeholder inside a format spec.
"""

from __future__ import annotations

import re
import string

RUN_NAMES = frozenset({"delivery_day", "next_delivery_day", "scheduled_for"})
"""Names a first-stage template (URL, query, header, SOAP ``params``) may use."""

MONTH_NAMES = frozenset({"month_start", "month_end"})
"""Indexed names: the first / last civil day of the month ``k`` months before the delivery day's."""

MAX_MONTHS_BACK = 12

_MONTH_FIELD = re.compile(r"(month_start|month_end)\[(\d{1,2})\]")
_FORMATTER = string.Formatter()


class TemplateError(ValueError):
    """A template uses a name or a field shape that is not allowed."""


def check_template(template: str, *, names: frozenset[str], month_index: bool) -> None:
    """Refuse anything but ``{name}`` / ``{name:spec}`` with ``name`` in ``names`` (and, when
    ``month_index``, ``{month_start[k]:spec}`` / ``{month_end[k]:spec}`` with 0 ≤ k ≤ 12)."""
    try:
        parsed = list(_FORMATTER.parse(template))
    except ValueError as exc:
        raise TemplateError(f"malformed template {template!r}: {exc}") from exc
    for _literal, field, spec, conversion in parsed:
        if field is None:
            continue
        if conversion is not None:
            raise TemplateError(
                f"placeholder {{{field}!{conversion}}}: conversions are not allowed"
            )
        if spec and ("{" in spec or "}" in spec):
            raise TemplateError(
                f"placeholder {{{field}:{spec}}}: nested placeholders are not allowed"
            )
        month = _MONTH_FIELD.fullmatch(field)
        if month is not None and month_index:
            if int(month.group(2)) > MAX_MONTHS_BACK:
                raise TemplateError(
                    f"placeholder {{{field}}}: k must be 0…{MAX_MONTHS_BACK} (ADR-033 amendment 1)"
                )
            continue
        if "." in field or "[" in field:
            raise TemplateError(
                f"placeholder {{{field}}}: attribute and index access are not allowed"
                + (" (only month_start[k] / month_end[k])" if month_index else "")
            )
        if field not in names:
            allowed = sorted(names) + (
                [f"{m}[k]" for m in sorted(MONTH_NAMES)] if month_index else []
            )
            raise TemplateError(
                f"unknown placeholder {{{field}}}; only {', '.join(allowed) or 'none'} exist"
            )
