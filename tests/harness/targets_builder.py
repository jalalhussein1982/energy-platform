"""Build complete or deliberately broken targets in a temporary directory (05 negative tests).

A complete target is the ADR-027 surface with a real Bronze fixture (blob + entry) and a golden
with checked values; the manifest is the T1 example unless a caller passes another one.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from energy_platform.bronze import CaptureEntry, blob_key, capture_id, sha256_hex, write_fixture
from energy_platform.contracts.manifest import target_secret_name
from energy_platform.contracts.registry import Transport

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"

GOOD_PARSER = (
    "from decimal import Decimal\n"
    "\n"
    "from energy_platform.contracts import SourceRecord, XmlDocument\n"
    "\n"
    "\n"
    "class Parser:\n"
    "    def parse(self, doc: XmlDocument) -> list[SourceRecord]:\n"
    "        rows = []\n"
    "        for item in doc.root.find_all('Item'):\n"
    "            price = item.first('Price')\n"
    "            rows.append(SourceRecord({'Price': Decimal(price.text or '0')}, 'x'))\n"
    "        return rows\n"
)

GOOD_TEST = (
    "from pathlib import Path\n"
    "\n"
    "from energy_platform.contracts.golden import load_golden\n"
    "\n"
    "HERE = Path(__file__).parent\n"
    "\n"
    "\n"
    "def test_goldens_load() -> None:\n"
    "    for path in sorted((HERE / 'golden').glob('*.yaml')):\n"
    "        golden = load_golden(path)\n"
    "        assert (HERE.parent / 'fixtures' / golden.fixture).is_dir()\n"
)

GOOD_GOLDEN = (
    "fixture: ordinary_day\n"
    "checked_by: tests/harness/targets_builder.py (synthetic values, tests/synthetic.py)\n"
    "expect:\n"
    "  row_count: 192\n"
    "  rows:\n"
    "    - delivery_start_utc: 2026-09-17T22:00:00Z\n"
    "      resolution: PT15M\n"
    "      metric: price_vwap\n"
    "      value: '170.13'\n"
    "    - delivery_start_utc: 2026-09-17T22:00:00Z\n"
    "      resolution: PT15M\n"
    "      metric: volume_total\n"
    "      value: '120.275'\n"
    "  quality_events: [partition_status]\n"
)

SCHEDULED = datetime(2026, 9, 17, 22, 15, tzinfo=UTC)


def write_bronze_fixture(
    directory: Path,
    target_id: str,
    payload: bytes,
    *,
    content_type: str = "text/xml; charset=utf-8",
    transport: Transport = "soap",
    source_url: str = "https://www.ote-cr.cz/pw-data/services/PublicDataService",
) -> CaptureEntry:
    sha = sha256_hex(payload)
    entry = CaptureEntry(
        capture_id=capture_id(target_id, SCHEDULED, 1),
        target_id=target_id,
        scheduled_for=SCHEDULED,
        attempt=1,
        fetched_at=SCHEDULED,
        source_url=source_url,
        http_status=200,
        content_type=content_type,
        payload_sha256=sha,
        raw_ref=blob_key(sha),
        size=len(payload),
        content_changed=True,
        source_transport=transport,
    )
    write_fixture(directory, entry, payload)
    return entry


def make_target(
    root: Path,
    target_id: str = "good_target",
    *,
    manifest: Path = EXAMPLES / "manifests" / "ote_idm_soap.yaml",
    fixture: Path = EXAMPLES / "fixtures" / "ote_idm_soap",
    with_parser: bool = False,
    golden: str = GOOD_GOLDEN,
) -> Path:
    """A complete target under ``root/target_id`` built from the examples."""
    t = root / target_id
    (t / "tests" / "golden").mkdir(parents=True)
    (t / "fixtures").mkdir()
    (t / "__init__.py").write_text("")
    text = manifest.read_text(encoding="utf-8")
    declared = next(line for line in text.splitlines() if line.startswith("target_id:"))
    old_id = declared.split(":", 1)[1].strip()
    text = text.replace(declared, f"target_id: {target_id}")
    # a target's secretRef is scoped to its id (05 C-63): renaming the target renames it too
    text = text.replace(target_secret_name(old_id), target_secret_name(target_id))
    (t / "manifest.yaml").write_text(text)
    (t / "README.md").write_text(f"# {target_id}\n")
    if with_parser:
        (t / "parser.py").write_text(GOOD_PARSER)
    (t / "tests" / "__init__.py").write_text("")
    (t / "tests" / "test_golden.py").write_text(GOOD_TEST)
    (t / "tests" / "golden" / "ordinary_day.yaml").write_text(golden)
    shutil.copytree(fixture, t / "fixtures" / "ordinary_day")
    entry_path = t / "fixtures" / "ordinary_day" / "entry.json"
    entry = CaptureEntry.from_json(entry_path.read_text(encoding="utf-8"))
    entry_path.write_text(
        entry.model_copy(
            update={
                "target_id": target_id,
                "capture_id": capture_id(target_id, entry.scheduled_for, entry.attempt),
            }
        ).to_json(),
        encoding="utf-8",
    )
    return t
