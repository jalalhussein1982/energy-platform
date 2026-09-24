"""P5-D3: the chart's targets values are generated from the manifests at deploy time; a
`restricted` licence is refused (05 C-55)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from scripts.render_target_values import main, shift_cron_minutes, target_values

from tests.harness.targets_builder import make_target

REPO = Path(__file__).resolve().parents[2]


def _set_license(target: Path, text: str) -> None:
    manifest = target / "manifest.yaml"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    lines = [f"license: {text!r}" if line.startswith("license:") else line for line in lines]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_committed_targets_render_with_their_cadence_and_correction() -> None:
    targets, problems = target_values(REPO / "targets")
    assert problems == []
    by_id = {t["id"]: t for t in targets}
    assert {"ote_intraday_market", "ote_intraday_market_xlsx", "ceps_load", "ote_dam"} <= set(by_id)
    t1 = by_id["ote_intraday_market"]
    assert t1["cron"] == "*/15 * * * *" and t1["timezone"] == "Europe/Prague"
    assert t1["correction"] == {"cron": "7 3 * * *", "days": 3}  # once a day, ADR-033 amendment 3
    assert t1["manifest"] == "ote_intraday_market/manifest.yaml"
    assert t1["hosts"] == ["www.ote-cr.cz"]
    assert by_id["ote_dam"]["cron"] == "15 13-16 * * *"  # after publication, ADR-033 amendment 3


def test_restricted_license_is_refused_and_named(tmp_path: Path) -> None:
    root = tmp_path / "targets"
    make_target(root, "ote_ok")
    _set_license(make_target(root, "ote_restricted"), "Restricted: internal use only")
    targets, problems = target_values(root)
    assert [t["id"] for t in targets] == ["ote_ok"]
    assert len(problems) == 1 and "ote_restricted" in problems[0] and "C-55" in problems[0]


def test_main_prints_yaml_and_exits_one_on_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "targets"
    make_target(root, "ote_ok")
    assert main(["render_target_values.py", str(root)]) == 0
    doc = yaml.safe_load(capsys.readouterr().out)
    assert [t["id"] for t in doc["targets"]] == ["ote_ok"]
    _set_license(make_target(root, "ote_restricted"), "restricted")
    assert main(["render_target_values.py", str(root)]) == 1
    assert "ote_restricted" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("cron", "offset", "expected"),
    [
        ("*/15 * * * *", 3, "3-59/15 * * * *"),
        ("0 12-23 * * *", 3, "3 12-23 * * *"),
        ("7 * * * *", 5, "12 * * * *"),
        ("0,30 * * * *", 3, "3,33 * * * *"),
        ("58 * * * *", 5, "58 * * * *"),  # would wrap: unchanged
        ("*/2 * * * *", 3, "*/2 * * * *"),  # offset >= step: unchanged
        ("*/15 * * * *", 0, "*/15 * * * *"),
        ("1-5 * * * *", 3, "1-5 * * * *"),  # a range: unchanged
    ],
)
def test_process_cron_is_the_cadence_shifted(cron: str, offset: int, expected: str) -> None:
    assert shift_cron_minutes(cron, offset) == expected


def test_targets_carry_a_process_cron() -> None:
    targets, _ = target_values(REPO / "targets", process_offset=3)
    by_id = {t["id"]: t for t in targets}
    assert by_id["ote_intraday_market"]["process_cron"] == "3-59/15 * * * *"
    assert by_id["ote_dam"]["process_cron"] == "18 13-16 * * *"
