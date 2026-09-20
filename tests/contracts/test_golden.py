"""The golden file model (ADR-020; 05 C-16): rows or a quarantine, checked by a human, no floats."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from energy_platform.contracts.golden import GoldenError, GoldenFile, load_golden

ROW = {
    "delivery_start_utc": "2026-09-17T22:00:00Z",
    "resolution": "PT15M",
    "metric": "price_vwap",
    "value": "97.31",
}


def test_rows_golden_loads_with_decimal_values() -> None:
    g = GoldenFile.model_validate({"fixture": "day", "checked_by": "me", "expect": {"rows": [ROW]}})
    assert g.expect.rows[0].value == Decimal("97.31")
    assert g.expect.rows[0].dimensions is None


def test_empty_document_golden_loads() -> None:
    g = GoldenFile.model_validate(
        {"fixture": "empty_result", "checked_by": "me", "expect": {"row_count": 0}}
    )
    assert g.expect.rows == () and g.expect.row_count == 0 and g.expect.quarantine is None


def test_quarantine_golden_loads() -> None:
    g = GoldenFile.model_validate(
        {"fixture": "bad_header", "checked_by": "me", "expect": {"quarantine": "header"}}
    )
    assert g.expect.rows == () and g.expect.quarantine == "header"


@pytest.mark.parametrize(
    ("expect", "match"),
    [
        ({"rows": []}, "at least one row"),
        ({"row_count": 1}, "at least one row"),
        ({}, "at least one row"),
        ({"quarantine": "x", "rows": [ROW]}, "excludes rows"),
        ({"quarantine": "x", "row_count": 1}, "excludes rows"),
        ({"rows": [{**ROW, "value": 97.31}]}, "quoted string"),
        ({"rows": [{**ROW, "delivery_start_utc": "2026-09-17T22:00:00"}]}, "timezone"),
        ({"rows": [{**ROW, "resolution": "15min"}]}, "pattern"),
        ({"rows": [ROW], "extra": 1}, "extra"),
    ],
)
def test_bad_expect_rejected(expect: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        GoldenFile.model_validate({"fixture": "day", "checked_by": "me", "expect": expect})


def test_checked_by_required_and_non_blank() -> None:
    with pytest.raises(ValidationError, match="checked_by"):
        GoldenFile.model_validate({"fixture": "day", "expect": {"rows": [ROW]}})
    with pytest.raises(ValidationError, match="checked_by"):
        GoldenFile.model_validate({"fixture": "day", "checked_by": "  ", "expect": {"rows": [ROW]}})


def test_load_golden_rejects_non_mapping_and_bad_yaml(tmp_path: Path) -> None:
    p = tmp_path / "g.yaml"
    p.write_text("- a\n")
    with pytest.raises(GoldenError, match="mapping"):
        load_golden(p)
    p.write_text("a: [\n")
    with pytest.raises(GoldenError):
        load_golden(p)
