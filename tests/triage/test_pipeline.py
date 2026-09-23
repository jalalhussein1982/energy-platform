"""The drift-triage pipeline end to end with the stubbed LLM (D-10), 05 C-59 and C-61."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from energy_platform.contracts.manifest import parse_manifest, validate_manifest
from energy_platform.harness.goldens import run_pipeline
from energy_platform.triage import HeuristicStubBackend, UnavailableBackend, triage
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
