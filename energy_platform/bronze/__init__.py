"""Bronze: immutable source captures, the irreplaceable tier (ADR-002, ADR-021, ADR-024 §1).

A capture is two objects: a content-addressed **blob** (written once) and a **capture-log
entry** (metadata, 01 §6.1 names). The blob is written first; the entry second; the ledger row
(Phase 2 ``store``) only after both. Backends in this phase: memory (tests) and a directory
(demo, fixtures) and S3 (``s3.py``, over ``fetch.objectstore`` — ADR-032 Option B).
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
from energy_platform.bronze.s3 import S3BlobStore, S3CaptureLog
from energy_platform.bronze.store import (
    BlobStore,
    FileBlobStore,
    MemoryBlobStore,
    blob_key,
    sha256_hex,
)
from energy_platform.contracts.invalidation import Invalidation, invalidation_key

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
    "Invalidation",
    "MemoryBlobStore",
    "MemoryCaptureLog",
    "S3BlobStore",
    "S3CaptureLog",
    "blob_key",
    "capture_id",
    "entry_key",
    "import_fixture",
    "invalidation_key",
    "load_fixture",
    "sha256_hex",
    "write_fixture",
]
