"""energyctl: validate exit codes, capture without a database, demo end to end (db)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from energy_platform.bronze import FileCaptureLog
from energy_platform.cli import app
from energy_platform.store.postgres import PostgresStore

EX = Path("examples")
runner = CliRunner()


def test_validate_exit_codes_follow_the_status() -> None:
    ok = runner.invoke(app, ["validate", "-m", str(EX / "manifests/ote_idm_soap.yaml")])
    assert ok.exit_code == 0 and json.loads(ok.stdout)["status"] == "OK"
    adm = runner.invoke(app, ["validate", "-m", str(EX / "manifests/entsoe_rest_xml.yaml")])
    assert adm.exit_code == 2
    assert json.loads(adm.stdout)["missing"]["hosts"] == ["web-api.tp.entsoe.eu"]
    missing = runner.invoke(app, ["validate", "-m", "nope.yaml"])
    assert missing.exit_code == 1


def test_capture_from_a_fixture_needs_no_database(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "capture",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
            "--fixture",
            str(EX / "fixtures/ote_idm_soap"),
            "--bronze-dir",
            str(tmp_path),
        ],
        env={"ENERGY_PLATFORM_DSN": ""},
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["outcome"] == "ok" and report["created"] is True
    assert report["ledger_updated"] is False  # no database: reconciled later (ADR-024 §1)
    entries = FileCaptureLog(tmp_path).list("ote_idm_soap")
    assert len(entries) == 1 and entries[0].http_status == 200
    again = runner.invoke(
        app,
        [
            "capture",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
            "--fixture",
            str(EX / "fixtures/ote_idm_soap"),
            "--bronze-dir",
            str(tmp_path),
        ],
        env={"ENERGY_PLATFORM_DSN": ""},
    )
    assert json.loads(again.stdout)["outcome"] == "noop"


def test_capture_requires_exactly_one_source() -> None:
    result = runner.invoke(app, ["capture", "-m", str(EX / "manifests/ote_idm_soap.yaml")])
    assert result.exit_code == 1 and "--fixture" in result.output


def test_process_and_gaps_require_a_database() -> None:
    for verb in ("process", "gaps"):
        result = runner.invoke(
            app,
            [verb, "-m", str(EX / "manifests/ote_idm_soap.yaml")],
            env={"ENERGY_PLATFORM_DSN": ""},
        )
        assert result.exit_code == 1 and "database" in result.output


def test_backfill_is_live_only() -> None:
    result = runner.invoke(app, ["backfill", "-m", str(EX / "manifests/ote_idm_soap.yaml")])
    assert result.exit_code == 1 and "--live" in result.output


@pytest.mark.db
def test_demo_end_to_end(tmp_path: Path) -> None:
    dsn = os.environ.get("ENERGY_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("ENERGY_PLATFORM_TEST_DSN not set; run `make db-test`")
    result = runner.invoke(app, ["demo", "--dsn", dsn, "--bronze-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert result.output.rstrip().endswith("demo: OK")
    store = PostgresStore(dsn)
    try:
        idm = store.current_rows("ote.idm_continuous")
        assert len(idm) == 7 * 96  # 7 metrics; the two shared ones have one current copy each
        assert len(store.current_rows("ceps.load")) == 2 * 96
        kinds = {e.kind for e in store.quality_events()}
        assert kinds == {"partition_status", "unknown_field"}
        assert not [e for e in store.quality_events() if e.kind == "quarantine"]
        statuses = [e.message for e in store.quality_events(kind="partition_status")]
        # one per attempt: first process and the no-op replay, for each of the three targets
        assert statuses == ["2026-09-18: complete 96/96"] * 6
    finally:
        store.truncate_all()
        store.close()
