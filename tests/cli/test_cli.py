"""energyctl: validate exit codes, capture without a database, demo end to end (db)."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
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
        assert kinds == {"partition_status"}  # T2's display column is declared (ADR-034)
        assert not [e for e in store.quality_events() if e.kind == "quarantine"]
        statuses = [e.message for e in store.quality_events(kind="partition_status")]
        # one per attempt: first process and the no-op replay, for each of the three targets
        assert statuses == ["2026-09-18: complete 96/96"] * 6
    finally:
        store.truncate_all()
        store.close()


def test_recapture_is_live_only() -> None:
    result = runner.invoke(
        app, ["recapture", "-m", str(EX / "manifests/ote_idm_soap.yaml"), "--days", "3"]
    )
    assert result.exit_code == 1 and "--live" in result.output


def test_smoke_without_a_dsn_runs_the_pipeline_in_memory(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "smoke",
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
    assert report["ok"] is True and report["silver_rows"] == 192
    assert "in memory" in result.stderr


def test_smoke_fails_on_a_fixture_of_another_target(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "smoke",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
            "--fixture",
            str(EX / "fixtures/ceps_load_soap"),
            "--bronze-dir",
            str(tmp_path),
        ],
        env={"ENERGY_PLATFORM_DSN": ""},
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_storage_probe_needs_a_class_and_an_endpoint() -> None:
    no_class = runner.invoke(app, ["storage-probe"], env={"ENERGY_PLATFORM_S3_STORAGE_CLASS": ""})
    assert no_class.exit_code == 1 and "--storage-class" in no_class.output
    no_store = runner.invoke(
        app,
        ["storage-probe", "--storage-class", "COLD"],
        env={"ENERGY_PLATFORM_S3_ENDPOINT": ""},
    )
    assert no_store.exit_code == 1 and "ENERGY_PLATFORM_S3_ENDPOINT" in no_store.output


def test_bronze_env_error_is_reported_not_raised(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "capture",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
            "--fixture",
            str(EX / "fixtures/ote_idm_soap"),
        ],
        env={
            "ENERGY_PLATFORM_DSN": "",
            "ENERGY_PLATFORM_BRONZE": "s3",
            "ENERGY_PLATFORM_BRONZE_DIR": "",
        },
    )
    assert result.exit_code == 1 and "ENERGY_PLATFORM_S3_ENDPOINT" in result.output


@pytest.mark.db
def test_smoke_with_a_dsn_uses_and_drops_a_throwaway_schema(tmp_path: Path) -> None:
    """P5-D5: synthetic fixture rows never reach the real tables."""
    dsn = os.environ.get("ENERGY_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("ENERGY_PLATFORM_TEST_DSN not set; run `make db-test`")
    import psycopg

    result = runner.invoke(
        app,
        [
            "smoke",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
            "--fixture",
            str(EX / "fixtures/ote_idm_soap"),
            "--dsn",
            dsn,
            "--bronze-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["ok"] is True
    with psycopg.connect(dsn) as conn:
        schemas = conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'smoke_%'"
        ).fetchall()
        assert schemas == []
        public_rows = conn.execute("SELECT count(*) FROM observations").fetchone()
        assert public_rows is not None and public_rows[0] == 0


@pytest.mark.db
def test_gaps_with_freshness_writes_the_sli_row(tmp_path: Path) -> None:
    dsn = os.environ.get("ENERGY_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("ENERGY_PLATFORM_TEST_DSN not set; run `make db-test`")
    manifest = str(EX / "manifests/ote_idm_soap.yaml")
    common = ["--dsn", dsn, "--bronze-dir", str(tmp_path)]
    cap = runner.invoke(
        app, ["capture", "-m", manifest, "--fixture", str(EX / "fixtures/ote_idm_soap"), *common]
    )
    assert cap.exit_code == 0, cap.output
    assert runner.invoke(app, ["process", "-m", manifest, *common]).exit_code == 0
    gaps = runner.invoke(app, ["gaps", "-m", manifest, "--with-freshness", *common])
    assert gaps.exit_code == 0, gaps.output
    last = json.loads(gaps.stdout.strip().splitlines()[-1])
    assert last["target_id"] == "ote_idm_soap" and last["expected_periods"] == 96
    fresh = runner.invoke(app, ["freshness", "-m", manifest, *common])
    assert fresh.exit_code == 0 and json.loads(fresh.stdout)["status"] in {
        "complete",
        "partial",
        "late",
        "pending",
    }
    store = PostgresStore(dsn)
    try:
        rows = store.freshness_rows()
        assert len(rows) == 1 and rows[0].target_id == "ote_idm_soap"
    finally:
        store.truncate_all()
        store.close()


def test_restore_drill_needs_a_scratch_dsn_and_a_replica(tmp_path: Path) -> None:
    no_scratch = runner.invoke(
        app,
        ["restore-drill", "--replica-dir", str(tmp_path)],
        env={"ENERGY_PLATFORM_SCRATCH_DSN": ""},
    )
    assert no_scratch.exit_code == 1 and "--scratch-dsn" in no_scratch.output
    no_replica = runner.invoke(
        app,
        [
            "restore-drill",
            "--scratch-dsn",
            "postgresql:///x",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
        ],
        env={"ENERGY_PLATFORM_S3_REPLICA_ENDPOINT": ""},
    )
    assert no_replica.exit_code == 1 and "replica" in no_replica.output


@pytest.mark.db
def test_restore_drill_rebuilds_into_a_scratch_schema_and_matches_live(tmp_path: Path) -> None:
    """ADR-002 / ADR-024 §2 on a real server: live in public, scratch in its own schema."""
    dsn = os.environ.get("ENERGY_PLATFORM_TEST_DSN")
    if not dsn:
        pytest.skip("ENERGY_PLATFORM_TEST_DSN not set; run `make db-test`")
    import psycopg

    manifest = str(EX / "manifests/ote_idm_soap.yaml")
    common = ["--dsn", dsn, "--bronze-dir", str(tmp_path)]
    cap = runner.invoke(
        app, ["capture", "-m", manifest, "--fixture", str(EX / "fixtures/ote_idm_soap"), *common]
    )
    assert cap.exit_code == 0, cap.output
    assert runner.invoke(app, ["process", "-m", manifest, *common]).exit_code == 0
    drill = runner.invoke(
        app,
        [
            "restore-drill",
            "--scratch-dsn",
            dsn,
            "--scratch-schema",
            "drill_scratch",
            "-m",
            manifest,
            "--replica-dir",
            str(tmp_path),
            "--dsn",
            dsn,
        ],
    )
    assert drill.exit_code == 0, drill.output
    report = json.loads(drill.stdout)
    assert report["ok"] and report["targets"][0]["message"].startswith("identical")
    assert report["targets"][0]["scratch"]["rows"] == 192
    with psycopg.connect(dsn) as conn:
        n = conn.execute("SELECT count(*) FROM drill_scratch.observations").fetchone()
        assert n is not None and n[0] == 192
        conn.execute("DROP SCHEMA drill_scratch CASCADE")
    store = PostgresStore(dsn)
    try:
        store.truncate_all()
    finally:
        store.close()


def test_invalidate_writes_a_bronze_decision_beside_the_capture_log(tmp_path: Path) -> None:
    """ADR-038: the verb needs no database; it refuses a capture id that is not in the log."""
    from energy_platform.bronze import FileCaptureLog

    bronze_dir = tmp_path / "bronze"
    fixture = Path("targets/ote_intraday_market/fixtures/ordinary_day")
    captured = runner.invoke(
        app,
        [
            "capture",
            "-m",
            "targets/ote_intraday_market/manifest.yaml",
            "--fixture",
            str(fixture),
            "--bronze-dir",
            str(bronze_dir),
        ],
    )
    assert captured.exit_code == 0, captured.output
    entry = FileCaptureLog(bronze_dir).latest("ote_intraday_market")
    assert entry is not None
    result = runner.invoke(
        app,
        [
            "invalidate",
            "-m",
            "targets/ote_intraday_market/manifest.yaml",
            "--capture",
            entry.capture_id,
            "--reason",
            "test decision",
            "--by",
            "maintainer",
            "--bronze-dir",
            str(bronze_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    decisions = FileCaptureLog(bronze_dir).invalidations("ote_intraday_market")
    assert [d.capture_id for d in decisions] == [entry.capture_id]
    unknown = runner.invoke(
        app,
        [
            "invalidate",
            "-m",
            "targets/ote_intraday_market/manifest.yaml",
            "--capture",
            "ote_intraday_market:2000-01-01T000000Z:9",
            "--reason",
            "x",
            "--by",
            "y",
            "--bronze-dir",
            str(bronze_dir),
        ],
    )
    assert unknown.exit_code == 1 and "not found" in unknown.output


def test_validate_refuses_a_custom_parser_until_a_loader_exists(tmp_path: Path) -> None:
    from tests.harness.targets_builder import make_target

    root = tmp_path / "targets"
    make_target(root, "ote_probe", with_parser=True)
    result = runner.invoke(app, ["validate", "ote_probe", "--targets-root", str(root)])
    assert result.exit_code == 1
    assert "custom parsers are not loaded" in result.stdout
    make_target(root, "ote_plain")
    assert runner.invoke(app, ["validate", "ote_plain", "--targets-root", str(root)]).exit_code == 0


def test_r2_live_capture_without_an_instant_is_keyed_by_the_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 3 R2: ``capture --live`` with no ``--scheduled-for`` used ``now()``, so the run
    never matched its cron instant. The CronJob's own tick, passed as the Job name, is the
    run's instant; without a name the newest firing instant is."""
    from energy_platform import cli
    from energy_platform.fetch import Fetcher, FixtureTransport
    from tests.synthetic import ote_im_price_period_response

    def offline(manifest: object) -> Fetcher:
        return Fetcher(
            allowed_hosts=("www.ote-cr.cz",),
            transport=FixtureTransport(ote_im_price_period_response(date(2026, 9, 24))),
            offline=True,
            sleep=lambda s: None,
        )

    monkeypatch.setattr(cli, "_live_fetcher", offline)
    result = runner.invoke(
        app,
        [
            "capture",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
            "--live",
            "--bronze-dir",
            str(tmp_path),
        ],
        env={
            "ENERGY_PLATFORM_DSN": "",
            "ENERGY_PLATFORM_JOB_NAME": "ep-capture-ote-idm-soap-29838195",
        },
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["scheduled_for"].startswith("2026-09-24 23:15:00")  # the tick, not now()
    entries = FileCaptureLog(tmp_path).list("ote_idm_soap")
    assert len(entries) == 1 and entries[0].scheduled_for == datetime(
        2026, 9, 24, 23, 15, tzinfo=UTC
    )
    # no Job name: the newest firing instant of the */15 cadence, minute-exact
    again = runner.invoke(
        app,
        [
            "capture",
            "-m",
            str(EX / "manifests/ote_idm_soap.yaml"),
            "--live",
            "--bronze-dir",
            str(tmp_path),
        ],
        env={"ENERGY_PLATFORM_DSN": "", "ENERGY_PLATFORM_JOB_NAME": ""},
    )
    assert again.exit_code == 0, again.output
    when = datetime.fromisoformat(json.loads(again.stdout)["scheduled_for"])
    assert when.second == 0 and when.microsecond == 0 and when.minute % 15 == 0
