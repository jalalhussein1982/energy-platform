"""Bronze: immutable source captures, the irreplaceable tier (ADR-002, ADR-021, ADR-024 §1).

A capture is two objects: a content-addressed **blob** (written once) and a **capture-log
entry** (metadata, 01 §6.1 names). The blob is written first; the entry second; the ledger row
(Phase 2 ``store``) only after both. Backends in this phase: memory (tests) and a directory
(demo, fixtures). The S3 backend is ADR-032 (PROPOSED).
"""

from energy_platform.bronze.bronze import Bronze, BronzeError, BronzeObject, CaptureOutcome
from energy_platform.bronze.capture_log import (
    CaptureEntry,
    CaptureLog,
    FileCaptureLog,
    MemoryCaptureLog,
    capture_id,
    entry_key,
)
from energy_platform.bronze.fixtures import import_fixture, load_fixture, write_fixture
from energy_platform.bronze.store import (
    BlobStore,
    FileBlobStore,
    MemoryBlobStore,
    blob_key,
    sha256_hex,
)

__all__ = [
    "BlobStore",
    "Bronze",
    "BronzeError",
    "BronzeObject",
    "CaptureEntry",
    "CaptureLog",
    "CaptureOutcome",
    "FileBlobStore",
    "FileCaptureLog",
    "MemoryBlobStore",
    "MemoryCaptureLog",
    "blob_key",
    "capture_id",
    "entry_key",
    "import_fixture",
    "load_fixture",
    "sha256_hex",
    "write_fixture",
]
