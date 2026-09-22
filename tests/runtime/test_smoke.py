"""ADR-025 smoke gate on memory backends: passes on the right fixture, fails on the wrong one,
fails when the ledger is unreachable, never reuses a fixture across runs of the same store."""

from __future__ import annotations

from pathlib import Path

from energy_platform.bronze import Bronze, MemoryBlobStore, MemoryCaptureLog
from energy_platform.runtime import smoke
from energy_platform.store import MemoryStore, UnavailableStore
from tests.runtime.harness import T1, T3

FIXTURES = Path("examples/fixtures")


def fresh() -> Bronze:
    return Bronze(MemoryBlobStore(), MemoryCaptureLog())


def test_smoke_passes_on_the_targets_own_fixture() -> None:
    report = smoke(T1, FIXTURES / "ote_idm_soap", store=MemoryStore(), bronze=fresh())
    assert report.ok, report.message
    assert report.run_state == "processed" and report.silver_rows == 2 * 96
    assert report.target_id == "ote_idm_soap"


def test_smoke_fails_when_the_parser_cannot_produce_a_row() -> None:
    """The rollback drill's injected failure (P5-D13): a fixture from another target."""
    report = smoke(T1, FIXTURES / "ceps_load_soap", store=MemoryStore(), bronze=fresh())
    assert not report.ok and report.silver_rows == 0
    # a document the parser cannot read yields no rows (an empty document is a valid outcome,
    # P4-D6) — the gate still fails because the smoke demands at least one Silver row
    assert "no Silver row" in report.message


def test_smoke_fails_without_a_ledger() -> None:
    report = smoke(T1, FIXTURES / "ote_idm_soap", store=UnavailableStore(), bronze=fresh())
    assert not report.ok and "ledger" in report.message


def test_smoke_fails_on_an_unreadable_fixture(tmp_path: Path) -> None:
    report = smoke(T3, tmp_path, store=MemoryStore(), bronze=fresh())
    assert not report.ok and "fixture unreadable" in report.message


def test_smoke_is_repeatable_on_a_fresh_bronze_and_store() -> None:
    for _ in range(2):
        report = smoke(T3, FIXTURES / "ceps_load_soap", store=MemoryStore(), bronze=fresh())
        assert report.ok, report.message
