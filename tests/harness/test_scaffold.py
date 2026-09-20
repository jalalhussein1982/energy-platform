"""The scaffolder writes exactly the ADR-027 surface and nothing that passes as a target."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml

from energy_platform.contracts.manifest import Modality, load_manifest, validate_manifest
from energy_platform.harness.scaffold import ScaffoldError, scaffold_target
from energy_platform.harness.surface import check_root, completeness

SURFACE = {
    "__init__.py",
    "manifest.yaml",
    "README.md",
    "tests/__init__.py",
    "tests/test_golden.py",
    "tests/golden/ordinary_day.yaml",
}


def _files(target: Path) -> set[str]:
    return {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "modality", ["soap-xml", "dated-file", "html-table", "rest-json", "rest-xml"]
)
def test_scaffold_is_exactly_the_surface_and_structurally_valid(
    tmp_path: Path, modality: str
) -> None:
    result = scaffold_target(tmp_path, "probe_target", cast(Modality, modality))
    assert _files(result.target) == SURFACE
    assert (result.target / "fixtures").is_dir()
    manifest = load_manifest(result.target / "manifest.yaml")  # structurally valid skeleton
    assert manifest.target_id == "probe_target" and manifest.modality == modality
    assert validate_manifest(manifest).status == "ADMISSION_REQUIRED"
    assert result.admission_required


def test_scaffold_with_parser(tmp_path: Path) -> None:
    result = scaffold_target(tmp_path, "probe_target", "soap-xml", with_parser=True)
    assert _files(result.target) == SURFACE | {"parser.py"}


def test_registered_dataset_fills_units_and_dimensions(tmp_path: Path) -> None:
    result = scaffold_target(
        tmp_path, "probe_target", "soap-xml", dataset_id="ceps.load", host="www.ceps.cz"
    )
    text = (result.target / "manifest.yaml").read_text()
    manifest = load_manifest(result.target / "manifest.yaml")
    assert not result.admission_required
    assert set(manifest.contract.metrics) == {"load_incl_pumping", "load"}
    assert manifest.mapping.metrics["load"].unit == "MW"
    assert manifest.mapping.dimensions["area"] == "CZ"
    assert "aggregation_function: REPLACE_ME" in text  # constrained: the author chooses
    assert "source_version: {constant: REPLACE_ME}" in text  # version is in the identity key
    result_v = validate_manifest(manifest)
    assert result_v.status == "INVALID"  # placeholders disagree with the registry, honestly


def test_scaffold_is_not_a_target(tmp_path: Path) -> None:
    """05 C-13, C-14, C-16: placeholders, no fixture, unchecked golden."""
    result = scaffold_target(tmp_path, "probe_target", "soap-xml")
    problems = check_root(tmp_path)
    assert any("placeholder" in p for p in problems)
    assert any("no fixture" in p for p in completeness(result.target))


def test_scaffold_refuses_bad_id_and_existing_dir(tmp_path: Path) -> None:
    with pytest.raises(ScaffoldError, match="target id"):
        scaffold_target(tmp_path, "Bad", "soap-xml")
    scaffold_target(tmp_path, "probe_target", "soap-xml")
    with pytest.raises(ScaffoldError, match="already exists"):
        scaffold_target(tmp_path, "probe_target", "soap-xml")


def test_scaffold_never_writes_outside_the_target(tmp_path: Path) -> None:
    scaffold_target(tmp_path, "probe_target", "rest-json")
    assert {p.name for p in tmp_path.iterdir()} == {"probe_target"}


def test_placeholder_dataset_is_not_a_valid_id(tmp_path: Path) -> None:
    result = scaffold_target(tmp_path, "probe_target", "soap-xml")
    manifest = load_manifest(result.target / "manifest.yaml")
    assert list(validate_manifest(manifest).missing.datasets) == ["REPLACE_ME.dataset"]


def test_scaffold_quotes_every_unit_so_a_dimensionless_flag_stays_a_string(tmp_path: Path) -> None:
    """ote.dam's `emergency_state` has unit "1"; unquoted, YAML reads it as an int (Phase 4, E1)."""
    scaffold_target(tmp_path, "ote_dam", "soap-xml", dataset_id="ote.dam", host="www.ote-cr.cz")
    data = yaml.safe_load((tmp_path / "ote_dam" / "manifest.yaml").read_text(encoding="utf-8"))
    units = {m: spec["unit"] for m, spec in data["mapping"]["metrics"].items()}
    assert units["emergency_state"] == "1" and all(isinstance(u, str) for u in units.values())
