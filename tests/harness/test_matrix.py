"""docs/05-constraint-matrix.md is checked, not trusted: every row cites a test that exists,
every test path resolves, every Make target it names is real (05 §4: a row without both a gate
and a test is a defect of the document)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MATRIX = (REPO / "docs" / "05-constraint-matrix.md").read_text(encoding="utf-8")
ROW = re.compile(r"^\| (C-\d\d) \|(.*)\|\s*$", re.MULTILINE)
REF = re.compile(r"((?:tests/[\w/.-]+|test_\w+)\.py)(?:::(test_\w+))?")


def _rows() -> dict[str, str]:
    return {m.group(1): m.group(2) for m in ROW.finditer(MATRIX)}


def _defined_tests(path: Path) -> set[str]:
    return set(re.findall(r"^def (test_\w+)\(", path.read_text(encoding="utf-8"), re.MULTILINE))


def _resolve(path: str) -> Path:
    """A full `tests/...` path, or a bare file name that must be unique under tests/."""
    if path.startswith("tests/"):
        return REPO / path
    matches = sorted((REPO / "tests").rglob(path))
    assert len(matches) == 1, f"{path}: {len(matches)} matches under tests/"
    return matches[0]


def test_matrix_has_the_mandated_rows() -> None:
    rows = _rows()
    assert len(rows) >= 54 and rows.keys() == {f"C-{i:02d}" for i in range(1, len(rows) + 1)}
    text = MATRIX.lower()
    for phrase in (
        "hardcoded url",
        "naive datetime",
        "swallowed exception",
        "unbounded retry",
        "positional parsing",
        "duplicated utility",
        "new dependency",
        "missing fixture",
        "missing golden",
        "missing `license`",
        "host not in",
        "secret in code",
        "fetch code inside a target",
        "normalise code inside a target",
        "outbound http outside `energy_platform.fetch`",
        "workload without resource",
        "mutable image tag",
        "migration without a downgrade",
        "unregistered `dataset_id`",
        "registry edit inside a target pr",
        "file outside the target surface",
        "third-party import in `parser.py`",
        "suppression comment",
        "network call in a unit test",
        "redirect to a private address",
        "redirect to an unlisted host",
        "`http` scheme",
        "metadata",
    ):
        assert phrase in text, phrase


def test_every_row_cites_an_existing_test() -> None:
    for row_id, body in _rows().items():
        refs = REF.findall(body)
        assert refs, f"{row_id} cites no test"
        for path, name in refs:
            file = _resolve(path)
            assert file.is_file(), f"{row_id}: {path} does not exist"
            if name:
                assert name in _defined_tests(file), f"{row_id}: {path}::{name} does not exist"


def test_every_make_target_in_the_inventory_exists() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.MULTILINE))
    inventory = MATRIX[MATRIX.index("## 2. Gate inventory") : MATRIX.index("## 3.")]
    for name in re.findall(r"^\| `([a-z][a-z0-9-]*)`", inventory, re.MULTILINE):
        assert name in targets, name
    assert {
        "harness-check",
        "pr-surface",
        "validate-targets",
        "migration-check",
        "workload-check",
    } <= targets


def test_negative_tests_live_in_the_harness_directory() -> None:
    harness = {p.name for p in (REPO / "tests" / "harness").glob("test_*.py")}
    for expected in (
        "test_target_surface.py",
        "test_target_collection.py",
        "test_goldens.py",
        "test_scaffold.py",
        "test_cli_harness.py",
        "test_pr_surface.py",
        "test_workloads.py",
        "test_migrations_gate.py",
        "test_ci_wrappers.py",
        "test_deps_allowlist.py",
        "test_ruff_gates.py",
        "test_mcp.py",
        "test_pr_bundle.py",
        "test_network_block.py",
        "test_secret_scan.py",
    ):
        assert expected in harness, expected
