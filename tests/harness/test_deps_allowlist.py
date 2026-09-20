"""05 C-38: a package in uv.lock that is not allowlisted fails; the real lock passes."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_deps_allowlist import allowlist, lock_packages, main

REPO = Path(__file__).resolve().parents[2]

LOCK = """version = 1
[[package]]
name = "energy-platform"
version = "0.0.1"
[[package]]
name = "pydantic"
version = "2.0"
[[package]]
name = "{extra}"
version = "0.1"
"""


def test_repository_lock_is_fully_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    assert main(["x", "uv.lock", "deps-allowlist.txt"]) == 0


def test_unlisted_package_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPO)
    lock = tmp_path / "uv.lock"
    lock.write_text(LOCK.format(extra="requestz"))  # slopsquat (ADR-008)
    allow = tmp_path / "allow.txt"
    allow.write_text("pydantic\n")
    assert main(["x", str(lock), str(allow)]) == 1
    assert "requestz" in capsys.readouterr().out
    assert lock_packages(lock) == {"pydantic", "requestz"}
    assert allowlist(allow) == {"pydantic"}


def test_case_insensitive_and_comments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    lock = tmp_path / "uv.lock"
    lock.write_text(LOCK.format(extra="PyYAML"))
    allow = tmp_path / "allow.txt"
    allow.write_text("# comment\npydantic  # why\npyyaml\n")
    assert main(["x", str(lock), str(allow)]) == 0


def test_missing_allowlist_fails(tmp_path: Path) -> None:
    assert main(["x", str(tmp_path / "uv.lock"), str(tmp_path / "nope.txt")]) == 1
