"""The package version, and the implementation version built on it, that `derivation_id`
names (ADR-023 §1, amendment 3)."""

import tomllib
from pathlib import Path

import energy_platform


def test_package_version_matches_pyproject() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert energy_platform.__version__ == project["version"]


def test_implementation_version_is_the_package_version_plus_a_source_digest() -> None:
    version = energy_platform.implementation_version()
    assert version.startswith(energy_platform.__version__ + "+")
    assert (
        len(version.split("+", 1)[1]) == 12 and version == energy_platform.implementation_version()
    )
