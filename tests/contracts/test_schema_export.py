"""schemas/manifest.v1.json is exported from the model and must be current (ADR-017)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.export_manifest_schema import render

SCHEMA_PATH = Path("schemas/manifest.v1.json")


def test_committed_schema_is_current() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render(), "run `make schema` and commit"


def test_schema_declares_the_mandatory_fields() -> None:
    schema = json.loads(render())
    assert schema["title"] == "Manifest"
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["additionalProperties"] is False
    required = set(schema["required"])
    assert {
        "license",
        "terms_url",
        "allowed_hosts",
        "cadence",
        "modality",
        "fetch",
        "contract",
        "mapping",
        "history",
    } <= required
    fetch_props = schema["$defs"]["FetchBlock"]["properties"]
    assert set(fetch_props) == {"soap_xml", "dated_file", "html_table", "rest_json", "rest_xml"}
    assert set(schema["properties"]["modality"]["enum"]) == {
        "soap-xml",
        "dated-file",
        "html-table",
        "rest-json",
        "rest-xml",
    }
