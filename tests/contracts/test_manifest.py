"""Manifest model, loader and admission validation — positive paths (ADR-017, ADR-022)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from scripts.secret_scan import PATTERNS as SCAN_PATTERNS

from energy_platform.contracts.manifest import (
    SECRET_PATTERNS,
    Manifest,
    ValidationResult,
    load_manifest,
    validate_manifest,
)
from tests.contracts.manifest_fixtures import t1_manifest, t3_manifest


def test_t1_manifest_validates_structurally() -> None:
    m = Manifest.model_validate(t1_manifest())
    assert m.modality == "soap-xml"
    assert m.fetch.key == "soap_xml"
    assert m.fetch.urls() == ("https://www.ote-cr.cz/pw-data/services/PublicDataService",)
    assert m.allow_insecure is False
    assert m.mapping.metrics["volume_total"].sign == "as_published"
    assert m.mapping.metrics["volume_total"].decimal_separator == "dot"


def test_t1_is_admitted() -> None:
    result = validate_manifest(Manifest.model_validate(t1_manifest()))
    assert result == ValidationResult(status="OK")
    assert not result.missing


def test_t3_is_admitted_with_version_bound_to_source_version() -> None:
    m = Manifest.model_validate(t3_manifest())
    assert m.mapping.source_version is not None
    assert m.mapping.source_version.constant == "RT"
    assert validate_manifest(m).status == "OK"


def test_mapping_block_is_canonical_json() -> None:
    m = Manifest.model_validate(t1_manifest())
    block = m.mapping_block()
    text = json.dumps(block, sort_keys=True, separators=(",", ":"))
    assert json.loads(text) == block
    assert "None" not in text and "null" not in text  # exclude_none keeps the hash input tidy
    assert block["metrics"]["price_vwap"] == {
        "source": "Price",
        "unit": "EUR/MWh",
        "sign": "as_published",
        "decimal_separator": "dot",
    }


def test_load_manifest_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(t1_manifest(), sort_keys=False), encoding="utf-8")
    m = load_manifest(path)
    assert m.target_id == "ote_idm_soap"


def test_validation_result_shape_matches_adr_022() -> None:
    dumped = validate_manifest(Manifest.model_validate(t1_manifest())).model_dump()
    assert set(dumped) == {"status", "errors", "missing"}
    assert set(dumped["missing"]) == {"datasets", "metrics", "hosts", "insecure_hosts"}


def test_secret_patterns_stay_in_step_with_secret_scan() -> None:
    """The manifest check duplicates scripts/secret_scan.py regexes; they must not drift."""
    shared = set(SECRET_PATTERNS) & set(SCAN_PATTERNS)
    assert {
        "AWS access key id",
        "private key block",
        "bearer token",
        "generic assignment",
    } <= shared
    for key in shared:
        assert SECRET_PATTERNS[key].pattern == SCAN_PATTERNS[key].pattern, key
        assert isinstance(SECRET_PATTERNS[key], re.Pattern)
