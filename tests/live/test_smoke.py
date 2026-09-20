"""Nightly live smoke (ADR-020; plan P4-D10): one bounded read per committed target, shape only.

Never selected by ``make test`` (the ``live`` marker is deselected there and the socket block
stays on for everything else). ``make live-smoke`` runs it on a schedule outside PR CI. It proves
that each committed manifest still fetches a document the platform can decode and parse; it
asserts **no value**, so a source-side change of numbers can never fail it and a change of shape
(a renamed element, a moved header) always does.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from energy_platform.bronze import load_fixture
from energy_platform.contracts.manifest import load_manifest
from energy_platform.harness.fixtures import record_live
from energy_platform.harness.surface import target_dirs
from energy_platform.parse import decode, generic_parser
from energy_platform.parse.generic import required_source_fields

REPO = Path(__file__).resolve().parents[2]
TARGETS = target_dirs(REPO / "targets")


@pytest.mark.live
@pytest.mark.parametrize("target", TARGETS, ids=[t.name for t in TARGETS])
def test_committed_target_still_serves_a_parseable_document(target: Path) -> None:
    manifest = load_manifest(target / "manifest.yaml")
    # yesterday in the source timezone: complete for T1/T2/T3, published for E1 (its request
    # asks for the following day, ADR-033 §4); never today, so a rolling day cannot be empty
    when = datetime.now(UTC) - timedelta(days=1)
    with tempfile.TemporaryDirectory(prefix="live-smoke-") as tmp:
        scratch = Path(tmp) / target.name
        scratch.mkdir()
        (scratch / "manifest.yaml").write_bytes((target / "manifest.yaml").read_bytes())
        entry = record_live(scratch, manifest, "smoke", scheduled_for=when)
        assert entry.http_status == 200 and entry.size > 0
        _, payload = load_fixture(scratch / "fixtures" / "smoke")
        records = list(generic_parser(manifest).parse(decode(payload, manifest.contract.decode)))
    # shape only: the document decodes, and every record the generic parser found carries the
    # time fields the mapping needs; an empty document (E1 before publication) is a valid shape
    for record in records:
        assert all(name in record.fields for name in required_source_fields(manifest))
