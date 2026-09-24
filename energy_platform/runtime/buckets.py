"""``bucket-init``: the local profile's bucket bootstrap through the platform's own client
(ADR-036 amendment 4). Store A: Object Lock + versioning (the platform puts retention headers on
every PUT, so the bucket must accept them); store B: plain (the copy target). Idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass

from energy_platform.fetch.objectstore import ObjectStore


@dataclass(frozen=True, slots=True)
class BucketReport:
    bucket: str
    created: bool
    object_lock: bool
    versioning: bool


def bucket_init(store: ObjectStore, *, object_lock: bool) -> BucketReport:
    """Create the store's bucket if absent; with ``object_lock`` also enable versioning (Object
    Lock requires it; a bucket created with the lock header has it already, the call is a
    no-op that proves the gateway answers)."""
    created = store.create_bucket(object_lock=object_lock)
    if object_lock:
        store.put_bucket_versioning(enabled=True)
    return BucketReport(store.bucket, created, object_lock, object_lock)
