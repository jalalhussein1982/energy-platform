"""ADR-020 / 05 C-17: every golden of every target runs on `make test`; a wrong golden fails.

The parametrised test discovers ``targets/*/tests/golden/*.yaml`` at collection time (empty until
Phase 4). The negatives below build targets in a temporary directory from the examples.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from energy_platform.harness.goldens import discover, run_golden, run_target
from tests.harness.targets_builder import GOOD_GOLDEN, make_target, write_bronze_fixture
from tests.synthetic import soap_fault

REPO = Path(__file__).resolve().parents[2]
DISCOVERED = discover(REPO / "targets")


@pytest.mark.parametrize(
    ("target", "golden"), DISCOVERED, ids=[f"{t.name}/{g.name}" for t, g in DISCOVERED]
)
def test_committed_target_golden(target: Path, golden: Path) -> None:
    report = run_golden(target, golden)
    assert report.ok, "\n".join(report.problems)


# ------------------------------------------------------------------ control


def test_example_target_golden_passes(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (report,) = run_target(t)
    assert report.ok, report.problems
    assert report.observations == 192 and "partition_status" in report.events


def test_expected_quarantine_passes(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    write_bronze_fixture(t / "fixtures" / "fault", "good_target", soap_fault())
    (t / "tests" / "golden" / "fault.yaml").write_text(
        "fixture: fault\nchecked_by: me\nexpect: {quarantine: Fault}\n"
    )
    reports = {r.golden: r for r in run_target(t)}
    assert reports["fault.yaml"].ok, reports["fault.yaml"].problems


# ------------------------------------------------------------------ C-17 negatives


def _golden_with(text: str, old: str, new: str) -> str:
    assert old in text
    return text.replace(old, new)


def test_wrong_golden_value_fails(tmp_path: Path) -> None:
    t = make_target(tmp_path, golden=_golden_with(GOOD_GOLDEN, "'170.13'", "'-170.13'"))
    (report,) = run_target(t)
    assert not report.ok
    assert any("expected -170.13, got 170.13" in p for p in report.problems), report.problems


def test_missing_expected_row_fails(tmp_path: Path) -> None:
    t = make_target(
        tmp_path,
        golden=_golden_with(GOOD_GOLDEN, "2026-09-17T22:00:00Z", "2026-09-19T22:00:00Z"),
    )
    (report,) = run_target(t)
    assert any("no such row was produced" in p for p in report.problems), report.problems


def test_row_count_mismatch_fails(tmp_path: Path) -> None:
    t = make_target(tmp_path, golden=_golden_with(GOOD_GOLDEN, "row_count: 192", "row_count: 96"))
    (report,) = run_target(t)
    assert any("row_count: expected 96, got 192" in p for p in report.problems), report.problems


def test_quality_event_mismatch_fails(tmp_path: Path) -> None:
    t = make_target(
        tmp_path, golden=_golden_with(GOOD_GOLDEN, "[partition_status]", "[negative_value]")
    )
    (report,) = run_target(t)
    assert any("quality_events" in p for p in report.problems), report.problems


def test_expected_quarantine_that_does_not_happen_fails(tmp_path: Path) -> None:
    t = make_target(
        tmp_path, golden="fixture: ordinary_day\nchecked_by: me\nexpect: {quarantine: Fault}\n"
    )
    (report,) = run_target(t)
    assert any("expected a quarantine" in p for p in report.problems), report.problems


def test_unexpected_quarantine_fails(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    write_bronze_fixture(t / "fixtures" / "ordinary_day", "good_target", soap_fault())
    (report,) = run_target(t)
    assert any("was quarantined" in p for p in report.problems), report.problems


def test_wrong_source_version_fails(tmp_path: Path) -> None:
    t = make_target(
        tmp_path,
        golden=_golden_with(
            GOOD_GOLDEN,
            "      metric: price_vwap\n",
            "      metric: price_vwap\n      source_version: v2\n",
        ),
    )
    (report,) = run_target(t)
    assert any("no such row" in p for p in report.problems), report.problems
