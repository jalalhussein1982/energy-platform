"""The Bronze facade: capture (blob then entry) and read (hot then cold).

Ordering is the ADR-004 invariant: a capture is *complete* when the blob and the entry both
exist and the entry's ``payload_sha256`` matches the blob (ADR-024 §1). Anything after that —
the ledger row — is an index and may fail without losing the observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from energy_platform.bronze.capture_log import CaptureEntry, CaptureLog, Tier, capture_id
from energy_platform.bronze.store import BlobStore, blob_key, sha256_hex
from energy_platform.contracts.registry import Transport
from energy_platform.fetch.client import FetchResult


class BronzeError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CaptureOutcome:
    entry: CaptureEntry
    created: bool
    """``False`` when an entry for ``(target_id, scheduled_for)`` already existed (idempotent)."""


@dataclass(frozen=True, slots=True)
class BronzeObject:
    payload: bytes
    tier: Tier


def _sha_of_ref(raw_ref: str) -> str:
    return raw_ref.rsplit("/", 1)[-1]


class _Default:
    """Marker type for "no baseline given": the run's own previous attempt is the baseline."""


_SAME_RUN = _Default()


class Bronze:
    def __init__(self, blobs: BlobStore, log: CaptureLog, cold: BlobStore | None = None) -> None:
        self._hot = blobs
        self._cold = cold
        self._log = log

    @property
    def log(self) -> CaptureLog:
        return self._log

    def capture(
        self,
        *,
        target_id: str,
        scheduled_for: datetime,
        result: FetchResult,
        transport: Transport,
        force: bool = False,
        baseline: CaptureEntry | _Default | None = _SAME_RUN,
    ) -> CaptureOutcome:
        """Persist one fetch result; idempotent per ``(target_id, scheduled_for)`` unless forced.

        ``baseline`` is the capture this one is compared with: a 304 reuses its payload and
        ``content_changed`` is measured against it. The runtime passes the same delivery day's
        last HTTP 200 entry (``runtime.capture.capture_baseline``); by default it is this run's
        own previous attempt. Never the target's newest run, which fetched another resource.
        """
        existing = self._log.entries_for(target_id, scheduled_for)
        if existing and not force:
            return CaptureOutcome(existing[-1], created=False)
        attempt = len(existing) + 1
        previous = (
            (existing[-1] if existing else None) if isinstance(baseline, _Default) else baseline
        )

        if result.not_modified:
            if previous is None:
                raise BronzeError("304 Not Modified without a previous capture to point at")
            if previous.source_url != result.url:
                raise BronzeError(
                    f"304 Not Modified for a different resource than the baseline "
                    f"({result.url} vs {previous.source_url}): refusing to attach its payload"
                )
            sha, raw_ref, size = previous.payload_sha256, previous.raw_ref, previous.size
        else:
            sha = self._hot.put(result.body)  # 1. blob, content-addressed
            raw_ref, size = blob_key(sha), len(result.body)

        entry = CaptureEntry(  # 2. entry; the ledger row comes later and elsewhere
            capture_id=capture_id(target_id, scheduled_for, attempt),
            target_id=target_id,
            scheduled_for=scheduled_for,
            attempt=attempt,
            fetched_at=result.fetched_at,
            source_url=result.url,
            http_status=result.status,
            content_type=result.content_type,
            payload_sha256=sha,
            raw_ref=raw_ref,
            size=size,
            content_changed=previous is None or previous.payload_sha256 != sha,
            source_transport=transport,
            etag=result.etag if not result.not_modified else previous_etag(previous),
            last_modified=(
                result.last_modified if not result.not_modified else previous_lm(previous)
            ),
            hops=result.hops,
        )
        self._log.put(entry)
        return CaptureOutcome(entry, created=True)

    def ingest(self, entry: CaptureEntry, payload: bytes) -> None:
        """Store an already-described capture (a fixture): blob first, then entry."""
        if sha256_hex(payload) != entry.payload_sha256:
            raise BronzeError("payload does not match entry.payload_sha256")
        self._hot.put(payload)
        self._log.put(entry)

    def read(self, raw_ref: str) -> BronzeObject:
        """Hot first, then cold (ADR-021 §1). Verifies the content address on the way out."""
        sha = _sha_of_ref(raw_ref)
        data = self._hot.get(sha)
        tier: Tier = "hot"
        if data is None and self._cold is not None:
            data = self._cold.get(sha)
            tier = "cold"
        if data is None:
            raise BronzeError(f"{raw_ref}: blob missing from hot and cold stores")
        if sha256_hex(data) != sha:
            raise BronzeError(f"{raw_ref}: content does not match its address")
        return BronzeObject(payload=data, tier=tier)

    def verify(self, entry: CaptureEntry) -> bool:
        """ADR-024 §1: complete = blob present and its hash equals the entry's."""
        try:
            return self.read(entry.raw_ref).payload is not None
        except BronzeError:
            return False


def previous_etag(previous: CaptureEntry | None) -> str | None:
    return None if previous is None else previous.etag


def previous_lm(previous: CaptureEntry | None) -> str | None:
    return None if previous is None else previous.last_modified
