"""05 C-39…C-41: a target PR touches one targets/<id>/ and nothing else (ADR-022 Route A)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from scripts.check_pr_surface import changed_files, main

from energy_platform.harness.pr_surface import classify, report


def test_pure_target_pr_passes() -> None:
    s = classify(["targets/ote_dam/manifest.yaml", "targets/ote_dam/tests/golden/day.yaml"])
    assert s.kind == "target" and s.target_id == "ote_dam" and s.ok


def test_platform_pr_passes_this_gate() -> None:
    s = classify(
        ["energy_platform/fetch/client.py", "docs/adr/ADR-033-x.md", "targets/__init__.py"]
    )
    assert s.kind == "platform" and s.ok


def test_target_plus_platform_file_rejected() -> None:
    s = classify(["targets/ote_dam/manifest.yaml", "docs/06-source-verification.md"])
    assert not s.ok
    assert any("outside targets/ote_dam/" in p for p in s.problems), s.problems


def test_registry_edit_in_target_pr_rejected() -> None:
    """05 C-40: the failure mode ADR-022 names, reported by name."""
    s = classify(["targets/ote_dam/manifest.yaml", "energy_platform/contracts/registry.py"])
    assert not s.ok
    assert any("registry (ADR-022 Route B)" in p for p in s.problems), s.problems


@pytest.mark.parametrize(
    "path",
    [
        "energy_platform/contracts/hosts.py",
        "deps-allowlist.txt",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "Makefile",
        "CODEOWNERS",
        "conftest.py",
        "scripts/check_target_surface.py",
        "deployment/helm/values.yaml",
    ],
)
def test_protected_paths_named_in_target_pr(path: str) -> None:
    s = classify(["targets/ote_dam/manifest.yaml", path])
    assert not s.ok and any(path in p and "05 C-40" in p for p in s.problems), s.problems


def test_two_targets_in_one_pr_rejected() -> None:
    s = classify(["targets/ote_dam/manifest.yaml", "targets/ceps_load/manifest.yaml"])
    assert not s.ok and any("05 C-41" in p for p in s.problems)


def test_empty_diff_is_reported_not_rejected() -> None:
    s = classify([])
    assert s.kind == "empty" and s.ok and report(s) == ["pr-surface: no changed files"]


def test_report_lists_every_problem() -> None:
    s = classify(["targets/a_target/x.py", "README.md"])
    lines = report(s)
    assert lines[0].startswith("pr-surface: REJECTED") and len(lines) == 2


# ------------------------------------------------------------------ git integration


def _git(cwd: Path, *args: str) -> str:
    git = shutil.which("git") or "/usr/bin/git"
    return subprocess.run(  # noqa: S603 — fixed argv in a temporary repository
        [git, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
            "HOME": str(cwd),
            "PATH": "/usr/bin:/bin",
        },
    ).stdout


def test_git_diff_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The script classifies `git diff --name-only <base>...HEAD` of a real repository."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "README.md").write_text("x\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD").strip()
    _git(tmp_path, "checkout", "-q", "-b", "target/ote_dam")
    (tmp_path / "targets" / "ote_dam").mkdir(parents=True)
    (tmp_path / "targets" / "ote_dam" / "manifest.yaml").write_text("schema_version: 1\n")
    (tmp_path / "energy_platform").mkdir()
    (tmp_path / "energy_platform" / "contracts.py").write_text("x = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "mixed")
    monkeypatch.chdir(tmp_path)
    assert changed_files(base) == ["energy_platform/contracts.py", "targets/ote_dam/manifest.yaml"]
    assert main(["x", "--base", base]) == 1
    _git(tmp_path, "rm", "-q", "energy_platform/contracts.py")
    _git(tmp_path, "commit", "-q", "-m", "clean")
    assert main(["x", "--base", base]) == 0


def test_no_base_is_an_honest_skip(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PR_BASE", raising=False)
    assert main(["x"]) == 0
    assert "nothing to classify" in capsys.readouterr().out
