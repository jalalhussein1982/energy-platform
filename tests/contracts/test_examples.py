"""The six example manifests: structurally valid; admitted or ADMISSION_REQUIRED as documented."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from energy_platform.contracts.manifest import Manifest, load_manifest, validate_manifest

EXAMPLES = Path("examples/manifests")

EXPECTED: dict[str, tuple[str, str]] = {
    # file → (modality, expected validation status)
    "ote_idm_soap.yaml": ("soap-xml", "OK"),
    "ote_idm_xlsx.yaml": ("dated-file", "OK"),
    "ceps_load_soap.yaml": ("soap-xml", "OK"),
    "ote_idm_html_table.yaml": ("html-table", "OK"),
    "token_api_rest_json.yaml": ("rest-json", "ADMISSION_REQUIRED"),
    "entsoe_rest_xml.yaml": ("rest-xml", "ADMISSION_REQUIRED"),
}


def test_exactly_six_examples() -> None:
    assert {p.name for p in EXAMPLES.glob("*.yaml")} == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_validates(name: str) -> None:
    modality, status = EXPECTED[name]
    m = load_manifest(EXAMPLES / name)
    assert m.modality == modality
    result = validate_manifest(m)
    assert result.status == status, result
    if status == "OK":
        assert not result.missing
        assert result.errors == ()


def test_shape_only_manifests_report_exact_gaps() -> None:
    rest_json = validate_manifest(load_manifest(EXAMPLES / "token_api_rest_json.yaml"))
    assert rest_json.missing.datasets == ("example.rest_json",)
    assert rest_json.missing.metrics == (("example.rest_json", "value"),)
    assert rest_json.missing.hosts == ("api.example.invalid",)
    entsoe = validate_manifest(load_manifest(EXAMPLES / "entsoe_rest_xml.yaml"))
    assert entsoe.missing.datasets == ("entsoe.day_ahead_prices",)
    assert entsoe.missing.hosts == ("web-api.tp.entsoe.eu",)


def test_every_modality_and_decode_appears() -> None:
    manifests = [load_manifest(p) for p in EXAMPLES.glob("*.yaml")]
    assert {m.modality for m in manifests} == {
        "soap-xml",
        "dated-file",
        "html-table",
        "rest-json",
        "rest-xml",
    }
    assert {m.contract.decode for m in manifests} >= {"soap", "xlsx", "html-table", "json", "xml"}


def test_examples_round_trip_through_the_exported_schema_shape() -> None:
    """Every example dumps to JSON that re-validates: the schema describes what we ship."""
    for p in EXAMPLES.glob("*.yaml"):
        m = load_manifest(p)
        again = Manifest.model_validate(json.loads(m.model_dump_json()))
        assert again == m


def test_t2_uses_the_discovery_step_and_a_context_date() -> None:
    m = load_manifest(EXAMPLES / "ote_idm_xlsx.yaml")
    assert m.fetch.dated_file is not None
    assert m.fetch.dated_file.discovery is not None
    assert m.mapping.time.date is not None
    assert m.mapping.time.date.context == "delivery_day"


def test_html_table_uses_the_decimal_comma_rule() -> None:
    m = load_manifest(EXAMPLES / "ote_idm_html_table.yaml")
    assert all(x.decimal_separator == "comma" for x in m.mapping.metrics.values())
