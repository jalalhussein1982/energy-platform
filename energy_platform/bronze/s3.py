"""Bronze on an S3-compatible object store (ADR-032 Option B, ADR-002 layout, ADR-021 tiers).

:class:`S3BlobStore` and :class:`S3CaptureLog` implement the Phase 2 ``BlobStore`` /
``CaptureLog`` protocols over :class:`energy_platform.fetch.objectstore.ObjectStore`; the facade,
the fixtures and the key layout do not change. A second ``S3BlobStore`` on the cold bucket is the
``cold=`` argument of :class:`~energy_platform.bronze.bronze.Bronze` (hot → cold read path).

Keys carry ``scheduled_for`` and ``attempt`` (``captures/<t>/<Y>/<M>/<D>/<stamp>_<n>.json``), so
a window or the latest entry is decided from a listing alone and only the matching entries are
fetched (P2-D19). Entries round-trip verbatim, ``tier`` included; the tiering job rewrites it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from energy_platform.bronze.capture_log import CaptureEntry, entry_key
from energy_platform.bronze.store import blob_key, sha256_hex
from energy_platform.fetch.objectstore import ObjectStore

_STAMP = "%Y-%m-%dT%H%M%SZ"
ENTRY_CONTENT_TYPE = "application/json"

Instant = tuple[datetime, int]
"""``(scheduled_for, attempt)`` — the order of the capture log."""


class S3BlobStore:
    """Content-addressed blobs: ``HEAD`` first, ``PUT`` only when the address is new (P2-D18)."""

    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    def put(self, data: bytes) -> str:
        sha = sha256_hex(data)
        key = blob_key(sha)
        if self._store.head(key) is None:
            self._store.put(key, data)
        return sha

    def get(self, sha256: str) -> bytes | None:
        return self._store.get(blob_key(sha256))

    def exists(self, sha256: str) -> bool:
        return self._store.head(blob_key(sha256)) is not None


def _parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, _STAMP).replace(tzinfo=UTC)


def key_instant(key: str) -> Instant | None:
    """``(scheduled_for, attempt)`` from an entry key; ``None`` for an object that is not one."""
    name = key.rsplit("/", 1)[-1]
    if not name.endswith(".json"):
        return None
    stamp, sep, attempt = name[: -len(".json")].rpartition("_")
    if not sep:
        return None
    try:
        return _parse_stamp(stamp), int(attempt)
    except ValueError:
        return None


def _within(scheduled_for: datetime, since: datetime | None, until: datetime | None) -> bool:
    if since is not None and scheduled_for < since:
        return False
    return not (until is not None and scheduled_for >= until)


class S3CaptureLog:
    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    def put(self, entry: CaptureEntry) -> None:
        self._store.put(entry.key, entry.to_json().encode(), content_type=ENTRY_CONTENT_TYPE)

    def get(self, capture_id: str) -> CaptureEntry | None:
        try:
            target_id, stamp, attempt = capture_id.rsplit(":", 2)
            key = entry_key(target_id, _parse_stamp(stamp), int(attempt))
        except ValueError:
            return None
        return self._read(key)

    def entries_for(self, target_id: str, scheduled_for: datetime) -> tuple[CaptureEntry, ...]:
        day_prefix = entry_key(target_id, scheduled_for, 1).rsplit("_", 1)[0] + "_"
        return self._entries(k for k, _ in self._instants(day_prefix))

    def list(
        self, target_id: str, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[CaptureEntry, ...]:
        keys = (
            key
            for key, (scheduled_for, _) in self._instants(f"captures/{target_id}/")
            if _within(scheduled_for, since, until)
        )
        return self._entries(keys)

    def latest(self, target_id: str) -> CaptureEntry | None:
        instants = list(self._instants(f"captures/{target_id}/"))
        if not instants:
            return None
        key, _ = max(instants, key=lambda item: item[1])
        return self._read(key)

    # ------------------------------------------------------------------ internals

    def _instants(self, prefix: str) -> Iterable[tuple[str, Instant]]:
        for info in self._store.list(prefix):
            instant = key_instant(info.key)
            if instant is not None:
                yield info.key, instant

    def _entries(self, keys: Iterable[str]) -> tuple[CaptureEntry, ...]:
        found = [e for e in (self._read(k) for k in keys) if e is not None]
        return tuple(sorted(found, key=lambda e: (e.scheduled_for, e.attempt)))

    def _read(self, key: str) -> CaptureEntry | None:
        raw = self._store.get(key)
        return None if raw is None else CaptureEntry.from_json(raw.decode("utf-8"))
