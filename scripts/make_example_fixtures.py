"""Write the Phase 2 example fixtures: synthetic Bronze objects for T1, T2, T3 (01 §10).

Run from the repository root: `uv run python -m scripts.make_example_fixtures`. Each fixture is a
directory `examples/fixtures/<target_id>/` with `entry.json` (capture-log entry) and `blob`
(the payload), exactly what a capture writes (ADR-020). Values are invented; shapes follow the
live reads in docs/01-data-scope.md §3. Deterministic: rerunning produces identical files.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from tests.synthetic import ceps_load_response, ote_im_price_period_response, ote_xlsx

from energy_platform.bronze import CaptureEntry, blob_key, capture_id, sha256_hex, write_fixture
from energy_platform.contracts.manifest import load_manifest

ROOT = Path("examples")
SCHEDULED = datetime(2026, 9, 17, 22, 15, tzinfo=UTC)  # 00:15 Prague on the delivery day
DELIVERY_DAY = date(2026, 9, 18)
FETCHED = datetime(2026, 9, 17, 22, 15, 4, tzinfo=UTC)

PAYLOADS = {
    "ote_idm_soap": (ote_im_price_period_response(DELIVERY_DAY), "text/xml; charset=utf-8"),
    "ote_idm_xlsx": (
        ote_xlsx(DELIVERY_DAY),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "ceps_load_soap": (ceps_load_response(DELIVERY_DAY), "text/xml; charset=utf-8"),
}


def main() -> int:
    for target, (payload, content_type) in PAYLOADS.items():
        manifest = load_manifest(ROOT / "manifests" / f"{target}.yaml")
        sha = sha256_hex(payload)
        entry = CaptureEntry(
            capture_id=capture_id(target, SCHEDULED, 1),
            target_id=target,
            scheduled_for=SCHEDULED,
            attempt=1,
            fetched_at=FETCHED,
            source_url=manifest.fetch.urls()[0],
            http_status=200,
            content_type=content_type,
            payload_sha256=sha,
            raw_ref=blob_key(sha),
            size=len(payload),
            content_changed=True,
            source_transport=manifest.contract.source_transport,
        )
        write_fixture(ROOT / "fixtures" / target, entry, payload)
        print(f"{target}: {len(payload)} bytes, sha256 {sha[:12]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
