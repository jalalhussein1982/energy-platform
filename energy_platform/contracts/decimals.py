"""Decimal-safe value parsing and the sign convention (ADR-019, 01 §9).

Czech sources render numbers with a decimal comma on HTML pages and with a dot in SOAP bodies
(01 §3). The separator is therefore declared per metric in the manifest and applied explicitly;
nothing is auto-detected, and ``float()`` is never called on a raw string.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

Separator = Literal["dot", "comma"]
Sign = Literal["as_published", "inverted"]

_PLAIN = re.compile(r"^[+-]?\d+(?:[.]\d+)?$")


def parse_decimal(value: str | Decimal | int | None, separator: Separator) -> Decimal | None:
    """Parse one source cell into a ``Decimal`` or ``None``.

    * ``None`` and blank strings are NULL ("not yet published" / "no trade"), never zero (01 §9).
    * Already-numeric cells (``Decimal``, ``int``) pass through: XLSX stores numbers natively.
    * Strings may contain digits, an optional leading sign and at most one occurrence of the
      declared separator. Thousands separators, exponents, ``NaN``/``inf`` and whitespace inside
      the number are rejected with ``ValueError`` so that the document is quarantined, not coerced.
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass; a flag is not a number here
        raise ValueError(f"not a decimal: {value!r}")
    if isinstance(value, Decimal | int):
        return Decimal(value)
    text = value.strip()
    if not text:
        return None
    if separator == "comma":
        if "." in text:
            raise ValueError(f"not a decimal under the comma rule: {value!r}")
        text = text.replace(",", ".", 1)
    if not _PLAIN.match(text):
        raise ValueError(f"not a decimal under the {separator} rule: {value!r}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # unreachable for _PLAIN matches; kept for safety
        raise ValueError(f"not a decimal: {value!r}") from exc


def apply_sign(value: Decimal | None, sign: Sign) -> Decimal | None:
    """Apply the manifest's sign convention. ``inverted`` negates; zero stays unsigned."""
    if value is None or sign == "as_published":
        return value
    negated = -value
    return negated if negated else abs(negated)
