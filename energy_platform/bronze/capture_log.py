"""The capture log: one JSON entry per capture attempt (ADR-002, ADR-024 §1, 01 §6.1).

Key: ``captures/<target_id>/<YYYY>/<MM>/<DD>/<scheduled_for>_<attempt>.json``. Idempotency of
the capture path is "does an entry for this ``(target_id, scheduled_for)`` exist"; attempt
numbers come from listing that prefix. No database is involved.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from energy_platform.contracts.invalidation import Invalidation
from energy_platform.contracts.registry import Transport

Tier = Literal["hot", "cold"]

_STAMP = "%Y-%m-%dT%H%M%SZ"


def _stamp(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime(_STAMP)


def capture_id(target_id: str, scheduled_for: datetime, attempt: int) -> str:
    return f"{target_id}:{_stamp(scheduled_for)}:{attempt}"


def entry_key(target_id: str, scheduled_for: datetime, attempt: int) -> str:
    utc = scheduled_for.astimezone(UTC)
    return f"captures/{target_id}/{utc:%Y}/{utc:%m}/{utc:%d}/{_stamp(scheduled_for)}_{attempt}.json"


class CaptureEntry(BaseModel):
    """Capture metadata. Field names follow 01 §6.1; no parser lineage here (ADR-002)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capture_id: str
    target_id: str
    scheduled_for: AwareDatetime
    attempt: int = Field(ge=1)
    fetched_at: AwareDatetime
    source_url: str
    http_status: int
    content_type: str | None
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_ref: str
    size: int = Field(ge=0)
    content_changed: bool
    source_transport: Transport
    source_published_at: AwareDatetime | None = None
    tier: Tier = "hot"
    etag: str | None = None
    last_modified: str | None = None
    hops: tuple[str, ...] = ()

    @field_validator("scheduled_for", "fetched_at", "source_published_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else v.astimezone(UTC)

    @property
    def key(self) -> str:
        return entry_key(self.target_id, self.scheduled_for, self.attempt)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> CaptureEntry:
        return cls.model_validate(json.loads(text))


class CaptureLog(Protocol):
    def put(self, entry: CaptureEntry) -> None:
        """Write (or overwrite) an entry: fixtures and ingest. The capture path never uses
        it (ADR-024 amendment 3)."""
        ...

    def put_new(self, entry: CaptureEntry) -> bool:
        """Create the entry only if its key does not exist yet; ``False`` when another
        writer got there first (ADR-024 amendment 3, review 2 DC-06). The capture path retries
        with the next attempt number, so no acknowledged entry is ever overwritten."""
        ...

    def get(self, capture_id: str) -> CaptureEntry | None: ...

    def entries_for(self, target_id: str, scheduled_for: datetime) -> tuple[CaptureEntry, ...]:
        """Every attempt for one scheduled instant, ordered by attempt."""
        ...

    def list(
        self, target_id: str, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[CaptureEntry, ...]:
        """Entries with ``since <= scheduled_for < until``, ordered by (scheduled_for, attempt)."""
        ...

    def latest(self, target_id: str) -> CaptureEntry | None:
        """Newest entry by (scheduled_for, attempt): the baseline for ``content_changed``."""
        ...

    def put_invalidation(self, inv: Invalidation) -> bool:
        """Record a durable invalidation decision beside the capture log (ADR-038): create
        only, ``False`` when that decision already exists. Never touches the capture."""
        ...

    def invalidations(self, target_id: str) -> tuple[Invalidation, ...]:
        """Every invalidation recorded for the target, ordered by key."""
        ...


def _ordered(entries: list[CaptureEntry]) -> tuple[CaptureEntry, ...]:
    return tuple(sorted(entries, key=lambda e: (e.scheduled_for, e.attempt)))


def _in_window(e: CaptureEntry, since: datetime | None, until: datetime | None) -> bool:
    if since is not None and e.scheduled_for < since:
        return False
    return not (until is not None and e.scheduled_for >= until)


class MemoryCaptureLog:
    def __init__(self) -> None:
        self._entries: dict[str, CaptureEntry] = {}
        self._invalidations: dict[str, Invalidation] = {}
        self._lock = threading.Lock()

    def put_invalidation(self, inv: Invalidation) -> bool:
        with self._lock:
            if inv.key in self._invalidations:
                return False
            self._invalidations[inv.key] = inv
            return True

    def invalidations(self, target_id: str) -> tuple[Invalidation, ...]:
        return tuple(
            self._invalidations[k]
            for k in sorted(self._invalidations)
            if self._invalidations[k].target_id == target_id
        )

    def put(self, entry: CaptureEntry) -> None:
        self._entries[entry.key] = entry

    def put_new(self, entry: CaptureEntry) -> bool:
        with self._lock:
            if entry.key in self._entries:
                return False
            self.put(entry)
            return True

    def get(self, capture_id: str) -> CaptureEntry | None:
        return next((e for e in self._entries.values() if e.capture_id == capture_id), None)

    def entries_for(self, target_id: str, scheduled_for: datetime) -> tuple[CaptureEntry, ...]:
        utc = scheduled_for.astimezone(UTC)
        return _ordered(
            [
                e
                for e in self._entries.values()
                if e.target_id == target_id and e.scheduled_for == utc
            ]
        )

    def list(
        self, target_id: str, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[CaptureEntry, ...]:
        return _ordered(
            [
                e
                for e in self._entries.values()
                if e.target_id == target_id and _in_window(e, since, until)
            ]
        )

    def latest(self, target_id: str) -> CaptureEntry | None:
        entries = self.list(target_id)
        return entries[-1] if entries else None


class FileCaptureLog:
    """Entries as files under ``<root>/captures/...``; listing walks the target's prefix."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, entry: CaptureEntry) -> None:
        path = self._root / entry.key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(entry.to_json(), encoding="utf-8")
        tmp.replace(path)

    def put_new(self, entry: CaptureEntry) -> bool:
        path = self._root / entry.key
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as f:  # O_EXCL: create or fail, atomically
                f.write(entry.to_json())
        except FileExistsError:
            return False
        return True

    def _all(self, target_id: str) -> list[CaptureEntry]:
        prefix = self._root / "captures" / target_id
        if not prefix.exists():
            return []
        return [
            CaptureEntry.from_json(p.read_text(encoding="utf-8"))
            for p in prefix.rglob("*.json")
            if not p.name.endswith(".tmp")
        ]

    def get(self, capture_id: str) -> CaptureEntry | None:
        target_id = capture_id.split(":", 1)[0]
        return next((e for e in self._all(target_id) if e.capture_id == capture_id), None)

    def entries_for(self, target_id: str, scheduled_for: datetime) -> tuple[CaptureEntry, ...]:
        utc = scheduled_for.astimezone(UTC)
        return _ordered([e for e in self._all(target_id) if e.scheduled_for == utc])

    def list(
        self, target_id: str, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[CaptureEntry, ...]:
        return _ordered([e for e in self._all(target_id) if _in_window(e, since, until)])

    def latest(self, target_id: str) -> CaptureEntry | None:
        entries = self.list(target_id)
        return entries[-1] if entries else None

    def put_invalidation(self, inv: Invalidation) -> bool:
        path = self._root / inv.key
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as f:
                f.write(inv.to_json())
        except FileExistsError:
            return False
        return True

    def invalidations(self, target_id: str) -> tuple[Invalidation, ...]:
        prefix = self._root / "invalidations" / target_id
        if not prefix.exists():
            return ()
        return tuple(
            Invalidation.from_json(p.read_text(encoding="utf-8"))
            for p in sorted(prefix.glob("*.json"))
        )
