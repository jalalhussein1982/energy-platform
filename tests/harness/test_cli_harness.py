"""energyctl harness verbs: validate by id, record-fixture, admission-request, run-target-tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from energy_platform.cli import app
from energy_platform.harness.scaffold import scaffold_target
from tests.harness.targets_builder import EXAMPLES, make_target

runner = CliRunner()
TEMPLATE = Path("docs/admissions/TEMPLATE.md")


def _run(*args: str, root: Path) -> tuple[int, str]:
    """Exit code and stdout+stderr (typer's `err=True` lines land in stderr)."""
    result = runner.invoke(app, [*args, "--targets-root", str(root)])
    return result.exit_code, result.output + result.stderr


# ------------------------------------------------------------------ validate <id>


def test_validate_by_id_ok_for_a_complete_target(tmp_path: Path) -> None:
    make_target(tmp_path, "ote_probe")
    code, out = _run("validate", "ote_probe", root=tmp_path)
    assert code == 0, out
    report = json.loads(out)
    assert report["validation"]["status"] == "OK" and report["surface"] == []


def test_validate_by_id_reports_admission_required(tmp_path: Path) -> None:
    """05 C-23: unregistered dataset → exit 2 with the exact gaps (ADR-022)."""
    make_target(tmp_path, "entsoe_probe", manifest=EXAMPLES / "manifests" / "entsoe_rest_xml.yaml")
    code, out = _run("validate", "entsoe_probe", root=tmp_path)
    assert code == 2
    report = json.loads(out)
    assert report["validation"]["status"] == "ADMISSION_REQUIRED"
    assert report["validation"]["missing"]["hosts"] == ["web-api.tp.entsoe.eu"]


def test_validate_rejects_missing_license(tmp_path: Path) -> None:
    """05 C-20."""
    t = make_target(tmp_path, "ote_probe")
    manifest = t / "manifest.yaml"
    manifest.write_text(
        "\n".join(
            line for line in manifest.read_text().splitlines() if not line.startswith("license:")
        )
    )
    code, out = _run("validate", "ote_probe", root=tmp_path)
    assert code == 1 and "license" in out


def test_validate_rejects_target_id_mismatch(tmp_path: Path) -> None:
    """05 C-19."""
    t = make_target(tmp_path, "ote_probe")
    manifest = t / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace("target_id: ote_probe", "target_id: other"))
    code, out = _run("validate", "ote_probe", root=tmp_path)
    assert code == 1 and "must equal the directory name" in out


def test_validate_by_id_fails_on_surface_violation(tmp_path: Path) -> None:
    t = make_target(tmp_path, "ote_probe")
    (t / "fetch.py").write_text("x = 1\n")
    code, out = _run("validate", "ote_probe", root=tmp_path)
    assert code == 1 and "outside the target surface" in out


def test_validate_all_is_the_ci_gate(tmp_path: Path) -> None:
    make_target(tmp_path, "ote_probe")
    make_target(tmp_path, "entsoe_probe", manifest=EXAMPLES / "manifests" / "entsoe_rest_xml.yaml")
    code, _ = _run("validate", "--all", root=tmp_path)
    assert code == 2
    (tmp_path / "entsoe_probe" / "manifest.yaml").unlink()
    code, _ = _run("validate", "--all", root=tmp_path)
    assert code == 1  # a directory without a manifest is not a target either


def test_validate_all_without_targets_says_so(tmp_path: Path) -> None:
    (tmp_path / "__init__.py").write_text("")
    code, out = _run("validate", "--all", root=tmp_path)
    assert code == 0 and "no targets yet" in out


def test_validate_needs_exactly_one_selector(tmp_path: Path) -> None:
    code, out = _run("validate", root=tmp_path)
    assert code == 1 and "target id or --manifest" in out


# ------------------------------------------------------------------ new-target


def test_new_target_scaffolds_and_points_to_route_b(tmp_path: Path) -> None:
    code, out = _run("new-target", "probe_target", "--modality", "soap-xml", root=tmp_path)
    assert code == 0, out
    assert (tmp_path / "probe_target" / "manifest.yaml").is_file()
    assert "admission-request" in out
    code, out = _run("new-target", "probe_target", "--modality", "soap-xml", root=tmp_path)
    assert code == 1 and "already exists" in out
    code, out = _run("new-target", "probe_target2", "--modality", "ftp", root=tmp_path)
    assert code == 1 and "unknown modality" in out


# ------------------------------------------------------------------ record-fixture (05 C-50)


def test_record_fixture_needs_live_or_file(tmp_path: Path) -> None:
    make_target(tmp_path, "ote_probe")
    code, out = _run("record-fixture", "ote_probe", "--name", "x", root=tmp_path)
    assert code == 1 and "--live or --from-file" in out


def test_record_fixture_from_file_writes_a_bronze_object(tmp_path: Path) -> None:
    t = make_target(tmp_path, "ote_probe")
    payload = tmp_path / "payload.xml"
    payload.write_bytes((EXAMPLES / "fixtures" / "ote_idm_soap" / "blob").read_bytes())
    code, out = _run(
        "record-fixture",
        "ote_probe",
        "--name",
        "second_day",
        "--from-file",
        str(payload),
        "--scheduled-for",
        "2026-09-18T22:15:00+00:00",
        root=tmp_path,
    )
    assert code == 0, out
    entry = json.loads(out)
    assert entry["target_id"] == "ote_probe" and entry["source_transport"] == "soap"
    assert (t / "fixtures" / "second_day" / "blob").is_file()
    assert (t / "fixtures" / "second_day" / "entry.json").is_file()
    code, out = _run(
        "record-fixture",
        "ote_probe",
        "--name",
        "second_day",
        "--from-file",
        str(payload),
        root=tmp_path,
    )
    assert code == 1 and "already exists" in out


def test_record_fixture_live_without_network_fails_closed(tmp_path: Path) -> None:
    """--live resolves the host itself; under the socket block (ADR-027 §4) that is the first
    thing to fail, and nothing is written."""
    make_target(tmp_path, "ote_probe")
    result = runner.invoke(
        app,
        [
            "record-fixture",
            "ote_probe",
            "--name",
            "live_day",
            "--live",
            "--targets-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError) and "ADR-027" in str(result.exception)
    assert not (tmp_path / "ote_probe" / "fixtures" / "live_day").exists()


# ------------------------------------------------------------------ run-target-tests


def test_run_target_tests_green_and_red(tmp_path: Path) -> None:
    t = make_target(tmp_path, "ote_probe")
    code, out = _run("run-target-tests", "ote_probe", root=tmp_path)
    assert code == 0, out
    assert "golden ordinary_day.yaml (ordinary_day): OK, 192 rows" in out
    golden = t / "tests" / "golden" / "ordinary_day.yaml"
    golden.write_text(golden.read_text().replace("'170.13'", "'1.00'"))
    code, out = _run("run-target-tests", "ote_probe", root=tmp_path)
    assert code == 1 and "expected 1.00, got 170.13" in out


# ------------------------------------------------------------------ admission-request (05 C-54)


def test_admission_request_lists_exactly_the_gaps(tmp_path: Path) -> None:
    make_target(tmp_path, "entsoe_probe", manifest=EXAMPLES / "manifests" / "entsoe_rest_xml.yaml")
    out_dir = tmp_path / "admissions"
    code, out = _run("admission-request", "entsoe_probe", "--out", str(out_dir), root=tmp_path)
    assert code == 0, out
    text = (out_dir / "entsoe_probe.md").read_text()
    assert "`ADMISSION_REQUIRED`" in text
    assert "`entsoe.day_ahead_prices`" in text
    assert "`web-api.tp.entsoe.eu`" in text
    assert "REPLACE_ME" in text  # the human parts stay for the human
    assert {p.name for p in out_dir.iterdir()} == {"entsoe_probe.md"}


def test_admission_request_for_an_admitted_target_says_route_a(tmp_path: Path) -> None:
    make_target(tmp_path, "ote_probe")
    code, out = _run(
        "admission-request", "ote_probe", "--out", str(tmp_path / "adm"), root=tmp_path
    )
    assert code == 0 and "Route A" in out


def test_scaffolded_target_completed_by_hand_passes_every_gate(tmp_path: Path) -> None:
    """The golden path end to end: scaffold → fill → fixture → golden → green."""
    scaffold_target(tmp_path, "ote_probe", "soap-xml", dataset_id="ote.idm_continuous")
    t = tmp_path / "ote_probe"
    import shutil

    shutil.rmtree(t)
    make_target(tmp_path, "ote_probe")  # the filled-in state
    code, out = _run("validate", "ote_probe", root=tmp_path)
    assert code == 0, out
    code, out = _run("run-target-tests", "ote_probe", root=tmp_path)
    assert code == 0, out
