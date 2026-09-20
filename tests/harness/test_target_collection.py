"""F02: a failing test under targets/<id>/tests/ must fail the default pytest run.

Runs pytest in an isolated directory that carries a copy of this repository's pytest
configuration, so the assertion is about the committed `testpaths`, not about a path argument.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _pytest_ini_block() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    opts = data["tool"]["pytest"]["ini_options"]
    lines = ["[tool.pytest.ini_options]"]
    for key, value in opts.items():
        if isinstance(value, list):
            rendered = ", ".join(f'"{v}"' for v in value)
            lines.append(f"{key} = [{rendered}]")
        else:
            lines.append(f'{key} = "{value}"')
    return "\n".join(lines) + "\n"


def _mkpydirs(pytester: pytest.Pytester, dotted: str) -> Path:
    """mkpydir does not create parents; build each package level."""
    path = Path()
    for part in dotted.split("/"):
        path = path / part
        pytester.mkpydir(str(path))
    return pytester.path / path


def test_testpaths_include_targets() -> None:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert "targets" in data["tool"]["pytest"]["ini_options"]["testpaths"]


def test_failing_target_test_fails_default_run(pytester: pytest.Pytester) -> None:
    pytester.makefile(".toml", pyproject=_pytest_ini_block())
    pytester.mkpydir("tests")
    target_tests = _mkpydirs(pytester, "targets/review_probe/tests")
    (target_tests / "test_rejected.py").write_text(
        "def test_always_fails() -> None:\n    raise AssertionError('probe collected')\n"
    )
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(failed=1)


def test_passing_target_test_is_collected(pytester: pytest.Pytester) -> None:
    pytester.makefile(".toml", pyproject=_pytest_ini_block())
    pytester.mkpydir("tests")
    target_tests = _mkpydirs(pytester, "targets/review_control/tests")
    (target_tests / "test_control.py").write_text("def test_ok() -> None:\n    assert True\n")
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=1)


# ---------------------------------------------- ADR-020: incomplete target fails collection


def _copy_root_conftest(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    # The editable install is not visible from a foreign cwd on every interpreter; the
    # repository root is what `make test` runs from.
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    pytester.makefile(".toml", pyproject=_pytest_ini_block())
    pytester.makeconftest((REPO / "conftest.py").read_text(encoding="utf-8"))
    pytester.mkpydir("tests")
    (pytester.path / "tests" / "test_control.py").write_text(
        "def test_ok() -> None:\n    assert True\n"
    )


def test_target_without_fixture_fails_collection(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_root_conftest(pytester, monkeypatch)
    target = _mkpydirs(pytester, "targets/probe_target/tests")
    (target.parent / "manifest.yaml").write_text("schema_version: 1\ntarget_id: probe_target\n")
    (target / "test_probe.py").write_text("def test_ok() -> None:\n    assert True\n")
    (target / "golden").mkdir()
    (target / "golden" / "day.yaml").write_text(
        "fixture: day\nchecked_by: x\nexpect: {quarantine: y}\n"
    )
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        ["*incomplete target(s) fail collection (ADR-020)*", "*no fixture*"]
    )


def test_target_without_golden_fails_collection(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_root_conftest(pytester, monkeypatch)
    target = _mkpydirs(pytester, "targets/probe_target/tests")
    (target.parent / "manifest.yaml").write_text("schema_version: 1\ntarget_id: probe_target\n")
    (target / "test_probe.py").write_text("def test_ok() -> None:\n    assert True\n")
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*no golden*"])


def test_complete_target_is_collected(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.harness.targets_builder import make_target

    _copy_root_conftest(pytester, monkeypatch)
    (pytester.path / "targets").mkdir()
    (pytester.path / "targets" / "__init__.py").write_text("")
    make_target(pytester.path / "targets", "probe_target")
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=2)
