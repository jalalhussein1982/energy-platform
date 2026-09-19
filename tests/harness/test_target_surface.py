"""ADR-027 §1-§2 negative tests: one bad target per rule, and one good target as the control."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_target_surface import check_root

GOOD_PARSER = (
    "from decimal import Decimal\n"
    "from energy_platform.contracts import parser\n"
    "\n"
    "class P:\n"
    "    def parse(self, doc: object) -> list[Decimal]:\n"
    "        return [Decimal('1')]\n"
)


def make_target(root: Path, target_id: str = "good_target") -> Path:
    t = root / target_id
    (t / "tests" / "golden").mkdir(parents=True)
    (t / "fixtures").mkdir()
    (t / "__init__.py").write_text("")
    (t / "manifest.yaml").write_text("schema_version: 1\n")
    (t / "README.md").write_text("# good\n")
    (t / "parser.py").write_text(GOOD_PARSER)
    (t / "tests" / "__init__.py").write_text("")
    (t / "tests" / "test_golden.py").write_text("def test_ok() -> None:\n    assert True\n")
    (t / "tests" / "golden" / "ordinary_day.yaml").write_text("rows: []\n")
    (t / "fixtures" / "blob.bin").write_bytes(b"x")
    return t


def test_control_target_passes(tmp_path: Path) -> None:
    make_target(tmp_path)
    assert check_root(tmp_path) == []


@pytest.mark.parametrize(
    ("relpath", "content", "reason"),
    [
        ("fetch.py", "x = 1\n", "file outside the target surface"),
        ("tests/conftest.py", "", "conftest.py is not allowed"),
        ("tests/helpers.py", "x = 1\n", "file outside the target surface"),
        ("tests/golden/notes.txt", "", "file outside the target surface"),
    ],
)
def test_file_outside_surface_rejected(
    tmp_path: Path, relpath: str, content: str, reason: str
) -> None:
    t = make_target(tmp_path)
    (t / relpath).write_text(content)
    problems = check_root(tmp_path)
    assert any(reason in p for p in problems), problems


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("import http.client\n", "import not allowed in a parser: http.client"),
        ("import socket\n", "import not allowed in a parser: socket"),
        ("import requests\n", "import not allowed in a parser: requests"),
        ("import lxml.etree\n", "import not allowed in a parser: lxml.etree"),
        ("from energy_platform.fetch import get\n", "import not allowed in a parser"),
        ("from . import helper\n", "relative import"),
    ],
)
def test_parser_import_outside_allowlist_rejected(tmp_path: Path, line: str, reason: str) -> None:
    t = make_target(tmp_path)
    (t / "parser.py").write_text(line + GOOD_PARSER)
    problems = check_root(tmp_path)
    assert any(reason in p for p in problems), problems


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("x = 1  # noqa: E501\n", "lint suppression"),
        ("x = 1  # type: ignore\n", "type suppression"),
        ("x = 1  # pragma: no cover\n", "coverage/pragma suppression"),
        ("mod = __import__('socket')\n", "dynamic import"),
        ("exec('print(1)')\n", "code execution"),
        ("f = open('/etc/passwd')\n", "file access"),
        ("g = getattr(__builtins__, 'open')\n", "builtins access"),
    ],
)
def test_suppression_or_escape_in_parser_rejected(tmp_path: Path, line: str, reason: str) -> None:
    t = make_target(tmp_path)
    (t / "parser.py").write_text(GOOD_PARSER + line)
    problems = check_root(tmp_path)
    assert any(reason in p for p in problems), problems


def test_skipped_golden_test_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "tests" / "test_golden.py").write_text(
        "import pytest\n\n@pytest.mark.skip\ndef test_ok() -> None:\n    assert True\n"
    )
    assert any("test skip" in p for p in check_root(tmp_path))


def test_non_empty_init_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "__init__.py").write_text("import socket\n")
    assert any("__init__.py must be empty" in p for p in check_root(tmp_path))


def test_bad_target_id_rejected(tmp_path: Path) -> None:
    make_target(tmp_path, "Bad-Id")
    assert any("target id must match" in p for p in check_root(tmp_path))


def test_stray_file_under_targets_root_rejected(tmp_path: Path) -> None:
    make_target(tmp_path)
    (tmp_path / "shared_utils.py").write_text("x = 1\n")
    assert any("only target directories" in p for p in check_root(tmp_path))
