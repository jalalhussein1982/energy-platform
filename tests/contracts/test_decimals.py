"""Explicit decimal-separator parsing and sign convention (ADR-019, 01 §9)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from energy_platform.contracts.decimals import apply_sign, parse_decimal

_decimals = st.decimals(
    allow_nan=False, allow_infinity=False, places=3, min_value=-(10**6), max_value=10**6
)


@given(_decimals)
def test_comma_roundtrip(d: Decimal) -> None:
    assert parse_decimal(str(d).replace(".", ","), "comma") == d


@given(_decimals)
def test_dot_roundtrip(d: Decimal) -> None:
    assert parse_decimal(str(d), "dot") == d


@pytest.mark.parametrize(
    "text", ["1,234.5", "1.234,5", "NaN", "inf", "1e3", "12 345", "abc", "1_0"]
)
def test_rejects_ambiguous_or_non_numeric(text: str) -> None:
    with pytest.raises(ValueError, match="decimal"):
        parse_decimal(text, "dot")


def test_dot_text_under_comma_rule_is_rejected() -> None:
    with pytest.raises(ValueError, match="decimal"):
        parse_decimal("170.13", "comma")


def test_comma_text_under_dot_rule_is_rejected() -> None:
    with pytest.raises(ValueError, match="decimal"):
        parse_decimal("170,13", "dot")


def test_blank_is_null_never_zero() -> None:
    assert parse_decimal("  ", "dot") is None
    assert parse_decimal("", "comma") is None
    assert parse_decimal(None, "comma") is None


def test_numeric_cells_pass_through() -> None:
    # XLSX cells arrive already numeric (01 §3 T2); the separator rule does not apply to them
    assert parse_decimal(Decimal("125.275"), "comma") == Decimal("125.275")
    assert parse_decimal(3, "dot") == Decimal(3)


def test_negative_and_zero_prices() -> None:
    assert parse_decimal("-0,01", "comma") == Decimal("-0.01")
    assert parse_decimal("0,00", "comma") == Decimal("0")


def test_no_float_precision_loss() -> None:
    a = parse_decimal("0,1", "comma")
    b = parse_decimal("0,2", "comma")
    assert a is not None and b is not None
    assert a + b == Decimal("0.3")


def test_precision_preserved() -> None:
    v = parse_decimal("129,550", "comma")
    assert v is not None
    assert str(v) == "129.550"


@given(_decimals)
def test_inversion_is_an_involution(d: Decimal) -> None:
    assert apply_sign(apply_sign(d, "inverted"), "inverted") == d


@given(_decimals)
def test_as_published_is_identity(d: Decimal) -> None:
    assert apply_sign(d, "as_published") == d


def test_sign_of_none_and_zero() -> None:
    assert apply_sign(None, "inverted") is None
    z = apply_sign(Decimal("0.000"), "inverted")
    assert z is not None
    assert not z.is_signed()
