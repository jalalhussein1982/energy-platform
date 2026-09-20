"""The package version is the single source used in `derivation_id` (ADR-023 §1)."""

import tomllib
from pathlib import Path

import energy_platform


def test_package_version_matches_pyproject() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert energy_platform.__version__ == project["version"]
