"""The drift-triage pipeline end to end with the stubbed LLM (D-10), 05 C-59 and C-61."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from energy_platform.contracts.manifest import parse_manifest, validate_manifest
from energy_platform.harness.goldens import run_pipeline
from energy_platform.triage import HeuristicStubBackend, UnavailableBackend, triage
from tests.harness.targets_builder import write_bronze_fixture
from tests.triage.builders import REPO, drifted_t1, t1_target


def _changed_lines(diff: str) -> tuple[list[str], list[str]]:
    lines = diff.splitlines()
    removed = [ln for ln in lines if ln.startswith("-") and not ln.startswith("---")]
    added = [ln for ln in lines if ln.startswith("+") and not ln.startswith("+++")]
    return removed, added


def test_renamed_field_yields_manifest_only_proposal(tmp_path: Path) -> None:
    target = t1_target(tmp_path)
    before = (target / "manifest.yaml").read_text(encoding="utf-8")
    capture = drifted_t1(tmp_path, rename="PriceAvg")
    outbox = tmp_path / "outbox"

    result = triage(target, capture, HeuristicStubBackend(), outbox)

    assert result.status == "proposed", result.refusals
    assert result.drift is not None
    assert [m.source for m in result.drift.missing_sources] == ["Price"]
    assert result.drift.unknown_fields == ("PriceAvg",)
    assert result.operations == ({"op": "rename_source", "metric": "price_vwap", "to": "PriceAvg"},)
    # the target on disk is untouched: triage writes a proposal file, nothing else
    assert (target / "manifest.yaml").read_text(encoding="utf-8") == before
    assert [p.name for p in outbox.iterdir()] == [result.proposal_path.name]  # type: ignore[union-attr]
    proposal = json.loads(result.proposal_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    assert proposal["path"] == "targets/ote_intraday_market/manifest.yaml"
    removed, added = _changed_lines(proposal["diff"])
    assert len(removed) == len(added) == 1
    assert "source: Price " in removed[0] and "source: PriceAvg " in added[0]
    assert "# absent element = no trade" in added[0]  # the line's comment survives the edit
    # the patched manifest validates and maps the drifted capture
    patched_text = before.replace("source: Price ", "source: PriceAvg ", 1)
    patched = parse_manifest(patched_text)
    assert validate_manifest(patched).status == "OK"
    outcome = run_pipeline(patched, capture)
    assert outcome.quarantine is None and outcome.observations
    assert "golden" in proposal["next"] and "by hand" in proposal["next"]


def test_no_drift_no_proposal(tmp_path: Path) -> None:
    target = t1_target(tmp_path)
    outbox = tmp_path / "outbox"
    result = triage(target, target / "fixtures" / "ordinary_day", HeuristicStubBackend(), outbox)
    assert result.status == "no_drift"
    assert not outbox.exists()


def test_llm_unavailable_returns_no_proposal(tmp_path: Path) -> None:
    """ADR-009 hard requirement: no model → no proposal; the data platform never depends on it."""
    target = t1_target(tmp_path)
    outbox = tmp_path / "outbox"
    result = triage(target, drifted_t1(tmp_path), UnavailableBackend(), outbox)
    assert result.status == "no_proposal"
    assert result.drift is not None and result.drift.drifted
    assert not outbox.exists()
    # nothing on the capture/process path imports the triage package
    for package in ("runtime", "fetch", "bronze", "parse", "mapping", "silver", "store", "ledger"):
        for module in (REPO / "energy_platform" / package).rglob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else []
                )
                assert not any(n.startswith("energy_platform.triage") for n in names), module


CEPS = REPO / "targets" / "ceps_load"


def _ceps_target(tmp: Path) -> Path:
    import shutil

    target = tmp / "targets" / "ceps_load"
    target.mkdir(parents=True)
    shutil.copy(CEPS / "manifest.yaml", target / "manifest.yaml")
    shutil.copytree(CEPS / "fixtures" / "ordinary_day", target / "fixtures" / "ordinary_day")
    return target


def test_review2_ae01_a_renamed_ceps_attribute_is_drift_not_health(tmp_path: Path) -> None:
    """Review 2 AE-01: `value1=` → `value1New=` keeps the row count and loses one metric; the
    inventory admits the platform's @attribute names, so the rename is seen."""
    target = _ceps_target(tmp_path)
    text = (CEPS / "fixtures" / "ordinary_day" / "blob").read_text(encoding="utf-8")
    drifted = tmp_path / "captures" / "ceps-renamed"
    write_bronze_fixture(drifted, "ceps_load", text.replace('value1="', 'value1New="').encode())
    result = triage(target, drifted, HeuristicStubBackend(), tmp_path / "outbox")
    assert result.status != "no_drift", result
    assert result.drift is not None and result.drift.drifted
    assert [m.source for m in result.drift.missing_sources] == ["@value1"]
    assert "@value1New" in result.drift.unknown_fields


def test_review2_ae01_a_renamed_required_ote_field_is_drift_not_an_empty_day(
    tmp_path: Path,
) -> None:
    """Review 2 AE-01: `<Date>` → `<DeliveryDate>` makes the generic parser recognise no record;
    the inventory falls back to the document's own record set and the report says so."""
    target = t1_target(tmp_path)
    drifted = drifted_t1(tmp_path, rename="DeliveryDate")  # renames Price by default; swap
    text = (target / "fixtures" / "ordinary_day" / "blob").read_text(encoding="utf-8")
    text = text.replace("<Date>", "<DeliveryDate>").replace("</Date>", "</DeliveryDate>")
    drifted = tmp_path / "captures" / "ote-date-renamed"
    write_bronze_fixture(drifted, "ote_intraday_market", text.encode("utf-8"))
    result = triage(target, drifted, HeuristicStubBackend(), tmp_path / "outbox")
    assert result.status != "no_drift", result
    assert result.drift is not None and result.drift.no_records
    assert [m.source for m in result.drift.missing_sources] == ["Date"]
    assert "DeliveryDate" in result.drift.unknown_fields
    assert result.drift.observations == 0
