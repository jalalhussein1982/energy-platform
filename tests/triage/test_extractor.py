"""The bounded extractor (ADR-008: untrusted data → bounded sample), 05 C-60."""

from __future__ import annotations

import json
from pathlib import Path

from energy_platform.contracts.manifest import load_manifest
from energy_platform.triage.extract import (
    MAX_RECORDS,
    MAX_SAMPLE_CHARS,
    MAX_VALUE_CHARS,
    clean,
    extract,
)
from tests.triage.builders import INJECTION, T1, drifted_html, html_target, t1_payload


def test_sample_is_bounded_and_data_only() -> None:
    manifest = load_manifest(T1 / "manifest.yaml")
    huge = t1_payload().replace("</Item>", f"<Note>{INJECTION * 40}</Note></Item>")
    sample = extract(manifest, huge.encode("utf-8"))
    serialised = sample.to_json()
    assert len(serialised) <= MAX_SAMPLE_CHARS
    assert len(sample.records) <= MAX_RECORDS
    assert set(json.loads(serialised)) == {
        "fields",
        "records",
        "dropped_fields",
        "parse_error",
        "truncated",
    }
    for record in sample.records:
        assert set(record) <= set(sample.fields)
        assert all(len(v) <= MAX_VALUE_CHARS for v in record.values())
    assert "Note" in sample.fields and "Price" in sample.fields
    assert INJECTION not in serialised  # only a truncated prefix can survive


def test_hostile_text_is_truncated_and_stripped(tmp_path: Path) -> None:
    text = "ok‮​\x07\nIGNORE\tINSTRUCTIONS" + "x" * 500
    cleaned = clean(text)
    assert len(cleaned) <= MAX_VALUE_CHARS and "\n" not in cleaned and "\t" not in cleaned
    assert not any(c in cleaned for c in "‮​\x07")
    # a column header that is a paragraph (or carries line breaks) never enters the inventory
    target = html_target(tmp_path)
    capture = drifted_html(tmp_path, hostile_header=INJECTION, hostile_cell=INJECTION)
    manifest = load_manifest(target / "manifest.yaml")
    sample = extract(manifest, (capture / "blob").read_bytes())
    assert sample.dropped_fields == 1
    assert INJECTION not in sample.fields
    assert "Avg price (EUR/MWh)" in sample.fields  # a human header is a legitimate name
    assert all(len(v) <= MAX_VALUE_CHARS for r in sample.records for v in r.values())
