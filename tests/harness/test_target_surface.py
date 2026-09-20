"""ADR-027 §1-§2 and 05 C-01…C-19 negative tests: one bad target per rule, one good control."""

from __future__ import annotations

from pathlib import Path

import pytest

from energy_platform.harness.surface import check_root, completeness
from tests.harness.targets_builder import GOOD_PARSER, make_target


def _problems(root: Path) -> list[str]:
    return check_root(root)


ROW = (
    "{delivery_start_utc: 2026-09-17T22:00:00Z, resolution: PT15M, metric: price_vwap, value: '1'}"
)


def _golden(*, checked_by: str | None = "me", rows: str = f"[{ROW}]") -> str:
    head = "fixture: ordinary_day\n"
    if checked_by is not None:
        head += f"checked_by: {checked_by!r}\n"
    return head + f"expect: {{rows: {rows}}}\n"


def _with_body(body: str) -> str:
    return GOOD_PARSER.replace("        return rows\n", body + "        return rows\n")


def _assert_rejected(root: Path, reason: str) -> None:
    problems = _problems(root)
    assert any(reason in p for p in problems), problems


# ------------------------------------------------------------------ control


def test_control_target_passes(tmp_path: Path) -> None:
    make_target(tmp_path, with_parser=True)
    assert _problems(tmp_path) == []


def test_control_without_parser_passes(tmp_path: Path) -> None:
    make_target(tmp_path)
    assert _problems(tmp_path) == []


# ------------------------------------------------------------------ C-11 surface


@pytest.mark.parametrize(
    ("relpath", "content", "reason"),
    [
        ("fetch.py", "x = 1\n", "file outside the target surface"),
        ("tests/conftest.py", "", "conftest.py is not allowed"),
        ("tests/helpers.py", "x = 1\n", "file outside the target surface"),
        ("tests/golden/notes.txt", "", "file outside the target surface"),
        ("fixtures/stray.bin", "", "file outside the target surface"),
        ("fixtures/ordinary_day/notes.txt", "", "file outside the target surface"),
    ],
)
def test_file_outside_surface_rejected(
    tmp_path: Path, relpath: str, content: str, reason: str
) -> None:
    t = make_target(tmp_path)
    (t / relpath).write_text(content)
    _assert_rejected(tmp_path, reason)


def test_non_empty_init_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "__init__.py").write_text("import socket\n")
    _assert_rejected(tmp_path, "__init__.py must be empty")


def test_bad_target_id_rejected(tmp_path: Path) -> None:
    make_target(tmp_path, "Bad-Id")
    _assert_rejected(tmp_path, "target id must match")


def test_stray_file_under_targets_root_rejected(tmp_path: Path) -> None:
    make_target(tmp_path)
    (tmp_path / "shared_utils.py").write_text("x = 1\n")
    _assert_rejected(tmp_path, "only target directories")


# ------------------------------------------------------------------ C-02, C-12 imports


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("import http.client\n", "import not allowed in a parser: http.client"),
        ("import socket\n", "import not allowed in a parser: socket"),
        ("import requests\n", "import not allowed in a parser: requests"),
        ("import lxml.etree\n", "import not allowed in a parser: lxml.etree"),
        ("import time\n", "import not allowed in a parser: time"),
        ("from energy_platform.fetch import get\n", "import not allowed in a parser"),
        ("from energy_platform.mapping import map_records\n", "import not allowed in a parser"),
        ("from . import helper\n", "relative import"),
    ],
)
def test_parser_import_outside_allowlist_rejected(tmp_path: Path, line: str, reason: str) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(line + GOOD_PARSER)
    _assert_rejected(tmp_path, reason)


# ------------------------------------------------------------------ C-01, C-05, C-07, C-10 tokens


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
        ("URL = 'https://www.ote-cr.cz/pw-data/services/PublicDataService'\n", "hardcoded URL"),
        ("URL = 'http://169.254.169.254/latest/meta-data'\n", "hardcoded URL"),
        ("v = float('1,5'.replace(',', '.'))\n", "float() on a raw value"),
        ("while True:\n    pass\n", "unbounded loop"),
    ],
)
def test_forbidden_token_in_parser_rejected(tmp_path: Path, line: str, reason: str) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(GOOD_PARSER + line)
    _assert_rejected(tmp_path, reason)


def test_hardcoded_url_in_target_code_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "tests" / "test_golden.py").write_text(
        "URL = 'https://www.ote-cr.cz/x'\n\ndef test_ok() -> None:\n    assert URL\n"
    )
    _assert_rejected(tmp_path, "hardcoded URL")


def test_float_call_in_parser_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(GOOD_PARSER.replace("Decimal(price.text or '0')", "float(1)"))
    _assert_rejected(tmp_path, "float() on a raw value")


def test_unbounded_loop_in_parser_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(GOOD_PARSER + "while 1:\n    break\n")
    _assert_rejected(tmp_path, "unbounded loop")


@pytest.mark.parametrize(
    ("relpath", "content", "reason"),
    [
        (
            "tests/test_golden.py",
            "import pytest\n\n@pytest.mark.skip\ndef test_ok() -> None:\n    assert True\n",
            "test skip",
        ),
        (
            "tests/test_golden.py",
            "import pytest\n\n@pytest.mark.xfail\ndef test_ok() -> None:\n    assert True\n",
            "test skip",
        ),
        ("tests/test_golden.py", "def test_ok() -> None:\n    assert True  # noqa\n", "lint"),
    ],
)
def test_suppression_or_escape_in_parser_rejected(
    tmp_path: Path, relpath: str, content: str, reason: str
) -> None:
    t = make_target(tmp_path)
    (t / relpath).write_text(content)
    _assert_rejected(tmp_path, reason)


def test_skipped_golden_test_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "tests" / "test_golden.py").write_text(
        "import pytest\n\ndef test_ok() -> None:\n    pytest.skip('later')\n"
    )
    _assert_rejected(tmp_path, "test skip")


# ------------------------------------------ C-03 normalise, C-04 positional, C-06 duplicate


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("        v = Decimal('1') * 1000\n", "multiplication"),
        ("        v = Decimal('1') / 4\n", "division"),
        ("        v = 7 // 4\n", "floor division"),
        ("        v = 10 ** 3\n", "power"),
        ("        v = -Decimal('1')\n", "sign flip"),
        ("        v = -len(rows)\n", "sign flip"),
        ("        d = datetime.now().astimezone()\n", "timezone conversion"),
        ("        d = datetime(2026, 1, 1, tzinfo=None)\n", "timezone conversion"),
        ("        d = timedelta(minutes=15)\n", "interval arithmetic"),
    ],
)
def test_normalise_code_in_parser_rejected(tmp_path: Path, body: str, reason: str) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text("from datetime import datetime, timedelta\n" + _with_body(body))
    _assert_rejected(tmp_path, reason)


def test_negative_literal_is_not_a_sign_flip(tmp_path: Path) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(_with_body("        v = -1\n"))
    assert not [p for p in _problems(tmp_path) if "sign flip" in p]


@pytest.mark.parametrize(
    "body",
    [
        "        first = rows[0]\n",
        "        last = rows[-1]\n",
        "        c = doc.root.find_all('Item')[3]\n",
    ],
)
def test_positional_subscript_in_parser_rejected(tmp_path: Path, body: str) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(_with_body(body))
    _assert_rejected(tmp_path, "positional access")


def test_name_subscript_is_not_positional(tmp_path: Path) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(_with_body("        d = {'a': 1}\n        v = d['a']\n"))
    assert not [p for p in _problems(tmp_path) if "positional" in p]


@pytest.mark.parametrize("name", ["parse_decimal", "interval_for_index", "local_day_intervals"])
def test_duplicated_platform_utility_rejected(tmp_path: Path, name: str) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text(GOOD_PARSER + f"\n\ndef {name}(x: str) -> str:\n    return x\n")
    _assert_rejected(tmp_path, f"duplicated platform utility {name!r}")


def test_parser_without_a_parser_class_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path, with_parser=True)
    (t / "parser.py").write_text("from decimal import Decimal\n\nx = Decimal('1')\n")
    _assert_rejected(tmp_path, "exactly one class with a parse() method")


# ------------------------------------------------------------------ C-13 placeholders


@pytest.mark.parametrize(
    ("relpath", "content"),
    [
        ("manifest.yaml", "schema_version: 1\ntarget_id: good_target\nlicense: REPLACE_ME\n"),
        ("tests/golden/ordinary_day.yaml", _golden(checked_by="TODO")),
        ("tests/test_golden.py", "def test_ok() -> None:\n    assert True  # FIXME later\n"),
    ],
)
def test_placeholder_left_in_target_rejected(tmp_path: Path, relpath: str, content: str) -> None:
    t = make_target(tmp_path)
    (t / relpath).write_text(content)
    _assert_rejected(tmp_path, "placeholder left in the target")


def test_placeholder_in_readme_is_allowed(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "README.md").write_text("# good_target\n\nTODO: describe the source.\n")
    assert _problems(tmp_path) == []


# ---------------------------------------------- C-14...C-16, C-18, C-19 completeness


def test_missing_fixture_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    for p in (t / "fixtures" / "ordinary_day").iterdir():
        p.unlink()
    (t / "fixtures" / "ordinary_day").rmdir()
    _assert_rejected(tmp_path, "no fixture")
    assert any("no fixture" in p for p in completeness(t))


def test_missing_golden_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "tests" / "golden" / "ordinary_day.yaml").unlink()
    _assert_rejected(tmp_path, "no golden")


def test_missing_test_module_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "tests" / "test_golden.py").unlink()
    _assert_rejected(tmp_path, "no tests/test_*.py")


def test_golden_pointing_at_unknown_fixture_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    golden = t / "tests" / "golden" / "ordinary_day.yaml"
    golden.write_text(golden.read_text().replace("fixture: ordinary_day", "fixture: dst_day"))
    _assert_rejected(tmp_path, "fixture 'dst_day' does not exist")


@pytest.mark.parametrize(
    "content",
    [
        _golden(rows="[]"),
        _golden(checked_by=" "),
        _golden(checked_by=None),
        _golden(rows=f"[{ROW.replace(chr(39) + '1' + chr(39), '97.31')}]"),
        _golden(rows=f"[{ROW.replace('T22:00:00Z', ' 22:00:00')}]"),
        "- not a mapping\n",
    ],
)
def test_empty_golden_rejected(tmp_path: Path, content: str) -> None:
    t = make_target(tmp_path)
    (t / "tests" / "golden" / "ordinary_day.yaml").write_text(content)
    _assert_rejected(tmp_path, "05 C-16")


def test_fixture_not_a_bronze_object_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "fixtures" / "ordinary_day" / "blob").write_bytes(b"tampered")
    _assert_rejected(tmp_path, "not a Bronze object")


def test_fixture_without_entry_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    (t / "fixtures" / "ordinary_day" / "entry.json").unlink()
    _assert_rejected(tmp_path, "not a Bronze object")


def test_target_id_mismatch_rejected(tmp_path: Path) -> None:
    t = make_target(tmp_path)
    manifest = t / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace("target_id: good_target", "target_id: other"))
    _assert_rejected(tmp_path, "must equal the directory name")
