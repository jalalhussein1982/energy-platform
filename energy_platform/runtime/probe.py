"""``storage-probe``: ADR-021 §3 — trust a storage class only after a ``PUT`` proved it.

A gateway may accept a lifecycle rule naming any class and never move a byte (V-6, V-12), so the
deploy-time probe writes one object with ``x-amz-storage-class`` and reads it back with
``HEAD``: ``400 InvalidArgument`` (Ceph RGW answers with an empty ``<Message>``), any other
error, or a ``HEAD`` that reports ``STANDARD`` (or nothing) for a non-``STANDARD`` request fails
the probe. The object stays in the bucket (``probe/…``; a Bronze writer never deletes).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from energy_platform.fetch.objectstore import ObjectStore, ObjectStoreError
from energy_platform.runtime.context import utc_now

STANDARD = "STANDARD"


@dataclass(frozen=True, slots=True)
class ProbeReport:
    ok: bool
    requested: str
    reported: str | None
    key: str
    message: str


def storage_probe(
    store: ObjectStore, storage_class: str, *, clock: Callable[[], datetime] = utc_now
) -> ProbeReport:
    requested = storage_class.strip().upper()
    key = f"probe/{clock().strftime('%Y%m%dT%H%M%SZ')}-{requested}"
    try:
        store.put(key, b"energy-platform storage-class probe\n", storage_class=requested)
    except ObjectStoreError as exc:
        return ProbeReport(False, requested, None, key, f"PUT refused: {exc}")
    try:
        info = store.head(key)
    except ObjectStoreError as exc:
        return ProbeReport(False, requested, None, key, f"HEAD failed: {exc}")
    if info is None:
        return ProbeReport(False, requested, None, key, "HEAD: object missing after PUT")
    reported = (info.storage_class or STANDARD).upper()
    if reported != requested:
        return ProbeReport(
            False, requested, reported, key, f"gateway stored {reported}, not {requested}"
        )
    note = "" if requested != STANDARD else " (STANDARD proves nothing about a cold class)"
    return ProbeReport(True, requested, reported, key, f"class {requested} confirmed{note}")
