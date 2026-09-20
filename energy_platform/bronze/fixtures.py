"""Fixtures are Bronze objects (ADR-020): a directory holding ``entry.json`` and ``blob``.

The same two files a capture writes to the object store, so a parser that passes on a fixture
passes on a real capture. ``energyctl record-fixture`` (Phase 3) writes them; ``energyctl
capture --fixture`` and ``demo`` replay them through the real fetch path.
"""

from __future__ import annotations

from pathlib import Path

from energy_platform.bronze.bronze import Bronze, BronzeError
from energy_platform.bronze.capture_log import CaptureEntry
from energy_platform.bronze.store import sha256_hex

ENTRY_FILE = "entry.json"
BLOB_FILE = "blob"


def write_fixture(directory: Path, entry: CaptureEntry, payload: bytes) -> None:
    if sha256_hex(payload) != entry.payload_sha256:
        raise BronzeError("fixture payload does not match the entry's payload_sha256")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / BLOB_FILE).write_bytes(payload)
    (directory / ENTRY_FILE).write_text(entry.to_json(), encoding="utf-8")


def load_fixture(directory: Path) -> tuple[CaptureEntry, bytes]:
    entry = CaptureEntry.from_json((directory / ENTRY_FILE).read_text(encoding="utf-8"))
    payload = (directory / BLOB_FILE).read_bytes()
    if sha256_hex(payload) != entry.payload_sha256:
        raise BronzeError(f"{directory}: blob does not match entry.payload_sha256")
    return entry, payload


def import_fixture(bronze: Bronze, directory: Path) -> CaptureEntry:
    """Put a fixture into a Bronze as if it had been captured (blob first, then entry)."""
    entry, payload = load_fixture(directory)
    bronze.ingest(entry, payload)
    return entry
