"""Content-addressed blob stores (ADR-002 layout ``bronze/blobs/<sha[:2]>/<sha>``).

A blob is written once; writing the same bytes again is a no-op that returns the same key, which
is what makes an orphan blob (ADR-024 §6, crash after PUT) harmless.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Protocol


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_key(sha256: str) -> str:
    """The immutable object key that ``raw_ref`` carries (01 §6.1)."""
    return f"bronze/blobs/{sha256[:2]}/{sha256}"


class BlobStore(Protocol):
    def put(self, data: bytes) -> str:
        """Store ``data``; return its SHA-256. Idempotent."""
        ...

    def get(self, sha256: str) -> bytes | None: ...

    def exists(self, sha256: str) -> bool: ...


class MemoryBlobStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, data: bytes) -> str:
        sha = sha256_hex(data)
        self._blobs.setdefault(sha, bytes(data))
        return sha

    def get(self, sha256: str) -> bytes | None:
        return self._blobs.get(sha256)

    def exists(self, sha256: str) -> bool:
        return sha256 in self._blobs

    def __len__(self) -> int:
        return len(self._blobs)


class FileBlobStore:
    """A directory laid out exactly like the object store (so ``rclone`` can mirror it)."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, sha256: str) -> Path:
        return self._root / blob_key(sha256)

    def put(self, data: bytes) -> str:
        sha = sha256_hex(data)
        path = self._path(sha)
        if path.exists():
            return sha
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)  # atomic: a reader never sees a partial blob
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return sha

    def get(self, sha256: str) -> bytes | None:
        path = self._path(sha256)
        return path.read_bytes() if path.exists() else None

    def exists(self, sha256: str) -> bool:
        return self._path(sha256).exists()
