"""``run_target_tests``: the goldens through the platform, then the target's own tests.

The golden runner needs no test framework; the target's ``tests/test_*.py`` run under pytest
in-process when pytest is importable (it is a dev dependency, not a runtime one), so the wheel
does not drag it in. Output is captured and returned, never printed by the library (T20).
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from pathlib import Path

from energy_platform.harness.goldens import GoldenReport, run_target
from energy_platform.harness.surface import check_target


@dataclass(frozen=True, slots=True)
class TargetTestReport:
    target_id: str
    surface: tuple[str, ...]
    goldens: tuple[GoldenReport, ...]
    pytest_exit: int | None
    pytest_output: str

    @property
    def ok(self) -> bool:
        return (
            not self.surface and all(g.ok for g in self.goldens) and self.pytest_exit in (0, None)
        )

    def lines(self) -> list[str]:
        out = [f"surface: {'OK' if not self.surface else 'violations'}"]
        out.extend(f"  {p}" for p in self.surface)
        for g in self.goldens:
            state = "OK" if g.ok else "FAIL"
            out.append(f"golden {g.golden} ({g.fixture}): {state}, {g.observations} rows")
            out.extend(f"  {p}" for p in g.problems)
        if self.pytest_exit is None:
            out.append("pytest: not available (dev group not installed)")
        else:
            out.append(f"pytest: exit {self.pytest_exit}")
        return out


def run_target_tests(target: Path, *, with_pytest: bool = True) -> TargetTestReport:
    surface = tuple(check_target(target))
    goldens = run_target(target)
    exit_code: int | None = None
    output = ""
    if with_pytest:
        exit_code, output = _pytest(target / "tests")
    return TargetTestReport(target.name, surface, goldens, exit_code, output)


def _pytest(tests_dir: Path) -> tuple[int | None, str]:
    try:
        import pytest
    except ImportError:
        return None, ""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = pytest.main(
            [
                "-q",
                "-p",
                "no:cacheprovider",
                "--import-mode=importlib",
                "-m",
                "not live",
                str(tests_dir),
            ]
        )
    return int(code), buf.getvalue()
