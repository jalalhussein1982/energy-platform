"""One negative test per structural rule and per ADR-022 admission gap."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from energy_platform.contracts.manifest import (
    Manifest,
    ManifestSyntaxError,
    load_manifest,
    validate_manifest,
)
from tests.contracts.manifest_fixtures import DELETE, t1_manifest, t3_manifest, with_


def _rejects(data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Manifest.model_validate(data)


# ----------------------------------------------------------------- structural (ADR-017/026/027)


def test_missing_license() -> None:
    _rejects(with_(t1_manifest(), "license", DELETE), "license")


def test_empty_license() -> None:
    _rejects(with_(t1_manifest(), "license", ""), "license")


def test_missing_terms_url() -> None:
    _rejects(with_(t1_manifest(), "terms_url", DELETE), "terms_url")


def test_terms_url_must_be_https() -> None:
    _rejects(with_(t1_manifest(), "terms_url", "http://www.ote-cr.cz/terms"), "https")


def test_empty_allowed_hosts() -> None:
    _rejects(with_(t1_manifest(), "allowed_hosts", []), "allowed_hosts")


def test_allowed_hosts_must_be_hostnames() -> None:
    _rejects(with_(t1_manifest(), "allowed_hosts", ["WWW.OTE-CR.CZ"]), "hostname")
    _rejects(with_(t1_manifest(), "allowed_hosts", ["10.0.0.1"]), "hostname")
    _rejects(with_(t1_manifest(), "allowed_hosts", ["*.ote-cr.cz"]), "hostname")


def test_url_host_must_be_in_allowed_hosts() -> None:
    data = with_(t1_manifest(), "fetch.soap_xml.url", "https://evil.example/soap")
    _rejects(data, "allowed_hosts")


def test_url_must_not_carry_a_port() -> None:
    data = with_(t1_manifest(), "fetch.soap_xml.url", "https://www.ote-cr.cz:8443/soap")
    _rejects(data, "port")


def test_http_without_allow_insecure() -> None:
    data = with_(t1_manifest(), "fetch.soap_xml.url", "http://www.ote-cr.cz/soap")
    _rejects(data, "allow_insecure")


def test_http_with_allow_insecure_is_structurally_valid_but_not_admitted() -> None:
    data = with_(t1_manifest(), "fetch.soap_xml.url", "http://www.ote-cr.cz/soap")
    data["allow_insecure"] = True
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "ADMISSION_REQUIRED"
    assert result.missing.insecure_hosts == ("www.ote-cr.cz",)


def test_ftp_scheme_rejected() -> None:
    data = with_(t1_manifest(), "fetch.soap_xml.url", "ftp://www.ote-cr.cz/soap")
    _rejects(data, "https")


def test_fetch_with_two_blocks() -> None:
    data = t1_manifest()
    data["fetch"]["html_table"] = {"url": "https://www.ote-cr.cz/x", "table_selector": "table"}
    _rejects(data, "exactly one")


def test_fetch_with_no_block() -> None:
    _rejects(with_(t1_manifest(), "fetch", {}), "exactly one")


def test_fetch_block_must_match_modality() -> None:
    _rejects(with_(t1_manifest(), "modality", "html-table"), "requires fetch.html_table")


def test_transport_must_match_modality() -> None:
    _rejects(with_(t1_manifest(), "contract.source_transport", "rest"), "source_transport")


def test_decode_must_match_modality() -> None:
    _rejects(with_(t1_manifest(), "contract.decode", "xlsx"), "decode")


def test_unknown_field_rejected() -> None:
    _rejects(with_(t1_manifest(), "parser", "custom"), "extra")


def test_schema_version_must_be_1() -> None:
    _rejects(with_(t1_manifest(), "schema_version", 2), "schema_version")


def test_bad_target_id() -> None:
    _rejects(with_(t1_manifest(), "target_id", "OTE-IDM"), "target_id")


def test_bad_cron_and_timezone() -> None:
    _rejects(with_(t1_manifest(), "cadence.cron", "every 15 minutes"), "cron")
    _rejects(with_(t1_manifest(), "cadence.timezone", "Prague"), "timezone")


def test_correction_window_validated() -> None:
    bad_cron = {"cron": "* * *", "days": 1}
    _rejects(with_(t1_manifest(), "cadence.correction", bad_cron), "five fields")
    _rejects(with_(t1_manifest(), "cadence.correction", {"cron": "7 * * * *", "days": 0}), "days")
    _rejects(with_(t1_manifest(), "cadence.correction", {"cron": "7 * * * *"}), "days")


def test_ignore_fields_may_not_name_a_mapped_source() -> None:
    _rejects(with_(t1_manifest(), "mapping.ignore_fields", ["Price"]), "mapped or ignored")
    _rejects(with_(t1_manifest(), "mapping.ignore_fields", ["PeriodIndex"]), "mapped or ignored")


def test_ignore_fields_are_names_not_positions() -> None:
    _rejects(with_(t1_manifest(), "mapping.ignore_fields", ["3"]), "positional")
    _rejects(with_(t1_manifest(), "mapping.ignore_fields", ["Emerg", "Emerg"]), "repeat")
    _rejects(with_(t1_manifest(), "mapping.ignore_fields", [" "]), "blank")


def test_bad_max_age() -> None:
    _rejects(with_(t1_manifest(), "history.max_age", "2 years"), "max_age")
    _rejects(with_(t1_manifest(), "history.max_age", "P"), "max_age")


def test_max_age_none_is_allowed() -> None:
    Manifest.model_validate(with_(t1_manifest(), "history.max_age", "none"))


def test_metrics_must_equal_mapping_keys() -> None:
    _rejects(with_(t1_manifest(), "contract.metrics", ["price_vwap"]), "must equal")


def test_duplicate_metrics() -> None:
    _rejects(with_(t1_manifest(), "contract.metrics", ["price_vwap", "price_vwap"]), "repeat")


def test_field_ref_exactly_one() -> None:
    _rejects(with_(t1_manifest(), "mapping.time.date", {"source": "Date", "constant": "x"}), "one")
    _rejects(with_(t1_manifest(), "mapping.time.date", {}), "one")


def test_time_kind_shape() -> None:
    _rejects(with_(t1_manifest(), "mapping.time.date", DELETE), "period_index")
    data = with_(t3_manifest(), "mapping.time.timestamp", DELETE)
    _rejects(data, "timestamp")


def test_constant_resolution_must_parse() -> None:
    _rejects(with_(t3_manifest(), "mapping.time.resolution", {"constant": "15min"}), "duration")


def test_decimal_separator_is_explicit() -> None:
    data = with_(t1_manifest(), "mapping.metrics.price_vwap.decimal_separator", "auto")
    _rejects(data, "decimal_separator")


@pytest.mark.parametrize(
    "value",
    [
        "AKIAIOSFODNN7EXAMPLE",  # secret-scan:allow — negative test input
        "Bearer abcdefghijklmnopqrstuvwxyz0123456789",  # secret-scan:allow
        "api_key=0123456789abcdef0123456789",  # secret-scan:allow
        "-----BEGIN RSA PRIVATE KEY-----",  # secret-scan:allow
        "a" * 40,
    ],
)
def test_credential_looking_string_in_fetch(value: str) -> None:
    data = with_(t1_manifest(), "fetch.soap_xml.params", {"token": value})
    _rejects(data, "credential")


def test_secret_ref_is_not_a_secret() -> None:
    data = t1_manifest()
    data["modality"] = "rest-json"
    data["fetch"] = {
        "rest_json": {
            "url_template": "https://www.ote-cr.cz/api",
            "auth": {
                "secretRef": {"name": "entsoe-token", "key": "token"},
                "location": "query",
                "param": "securityToken",
            },
        }
    }
    data["contract"]["source_transport"] = "rest"
    data["contract"]["decode"] = "json"
    Manifest.model_validate(data)


# ----------------------------------------------------------------- YAML subset (ADR-017)


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_yaml_anchor_rejected(tmp_path: Path) -> None:
    with pytest.raises(ManifestSyntaxError, match="anchors"):
        load_manifest(_write(tmp_path, "a: &x 1\nb: *x\n"))


def test_yaml_tag_rejected(tmp_path: Path) -> None:
    with pytest.raises(ManifestSyntaxError, match="tags"):
        load_manifest(_write(tmp_path, "a: !!python/object/apply:os.system ['id']\n"))


def test_yaml_multi_document_rejected(tmp_path: Path) -> None:
    with pytest.raises(ManifestSyntaxError, match="one YAML document"):
        load_manifest(_write(tmp_path, "---\na: 1\n---\nb: 2\n"))


def test_yaml_merge_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(ManifestSyntaxError, match=r"anchors|merge"):
        load_manifest(_write(tmp_path, "base: &b {x: 1}\na:\n  <<: *b\n"))


def test_yaml_scalar_document_rejected(tmp_path: Path) -> None:
    with pytest.raises(ManifestSyntaxError, match="mapping"):
        load_manifest(_write(tmp_path, "just a string\n"))


# ----------------------------------------------------------------- admission (ADR-022 §2)


def test_unregistered_dataset_id() -> None:
    data = with_(t1_manifest(), "contract.dataset_id", "ote.imbalance_settlement")
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "ADMISSION_REQUIRED"
    assert result.missing.datasets == ("ote.imbalance_settlement",)
    assert result.missing.metrics == (
        ("ote.imbalance_settlement", "price_vwap"),
        ("ote.imbalance_settlement", "volume_total"),
    )
    assert result.missing.hosts == ()


def test_unregistered_metric() -> None:
    data = with_(t1_manifest(), "contract.metrics", ["price_vwap", "volume_total", "price_median"])
    data["mapping"]["metrics"]["price_median"] = {"source": "Median", "unit": "EUR/MWh"}
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "ADMISSION_REQUIRED"
    assert result.missing.metrics == (("ote.idm_continuous", "price_median"),)
    assert result.missing.datasets == ()


def test_host_not_in_registry() -> None:
    data = with_(t1_manifest(), "allowed_hosts", ["www.ote-cr.cz", "mirror.example.org"])
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "ADMISSION_REQUIRED"
    assert result.missing.hosts == ("mirror.example.org",)


def test_unit_mismatch_is_invalid_not_admission() -> None:
    data = with_(t1_manifest(), "mapping.metrics.volume_total.unit", "MW")
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "INVALID"
    assert any("'MW'" in e and "'MWh'" in e for e in result.errors)
    assert not result.missing


def test_wrong_fixed_dimension_is_invalid() -> None:
    data = with_(t1_manifest(), "mapping.dimensions", {"bidding_zone": "DE"})
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "INVALID"
    assert any("bidding_zone" in e for e in result.errors)


def test_wrong_dimension_keys_is_invalid() -> None:
    data = with_(t1_manifest(), "mapping.dimensions", {"area": "CZ"})
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "INVALID"
    assert any("dimensions keys" in e for e in result.errors)


def test_unverified_aggregation_function_is_invalid() -> None:
    data = with_(t3_manifest(), "mapping.dimensions", {"area": "CZ", "aggregation_function": "MAX"})
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "INVALID"
    assert any("aggregation_function" in e for e in result.errors)


def test_version_identity_needs_source_version() -> None:
    data = with_(t3_manifest(), "mapping.source_version", DELETE)
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "INVALID"
    assert any("source_version" in e for e in result.errors)


def test_undeclared_resolution_is_invalid() -> None:
    data = with_(t3_manifest(), "mapping.time.resolution", {"constant": "PT60M"})
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "INVALID"
    assert any("PT60M" in e for e in result.errors)


def test_admission_gaps_and_errors_are_reported_together() -> None:
    data = with_(t1_manifest(), "mapping.metrics.volume_total.unit", "MW")
    data["allowed_hosts"] = ["www.ote-cr.cz", "mirror.example.org"]
    result = validate_manifest(Manifest.model_validate(data))
    assert result.status == "ADMISSION_REQUIRED"
    assert result.missing.hosts == ("mirror.example.org",)
    assert result.errors  # the unit error is not hidden behind the admission gap


def test_numeric_source_is_positional_parsing() -> None:
    """05 C-04: a column position is not a field name."""
    data = t1_manifest()
    data["mapping"]["metrics"]["price_vwap"]["source"] = "3"
    _rejects(data, "column position")
