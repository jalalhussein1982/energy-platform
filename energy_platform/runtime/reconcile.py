"""``reconcile``: Bronze is the truth, the ledger is rebuilt from it (ADR-024 §2, amendment 1)."""

from __future__ import annotations

from datetime import datetime, timedelta

from energy_platform.bronze import CaptureEntry
from energy_platform.runtime.context import Runtime
from energy_platform.store import Run


def _attempt_of(capture_id: str) -> int:
    return int(capture_id.rsplit(":", 1)[-1])


def reconcile(
    rt: Runtime, *, window: timedelta | None = None, now: datetime | None = None
) -> tuple[Run, ...]:
    """Insert missing ledger rows (``origin=reconciled``) for every capture-log entry in the
    window, and advance an existing run whose newest entry is a **later attempt with another
    payload** than the capture the run names (a correction captured while the ledger was down,
    review 2 DC-01): ``mark_recaptured`` makes it pending again and fences any in-flight
    claim. A later attempt with the run's own payload is a poll, not a generation. Returns the
    runs created or advanced. The window is widened by the manifest's correction days so a
    correction of D-3 captured during an outage is found too."""
    now = now or rt.clock()
    since = None
    if window is not None:
        correction = rt.manifest.cadence.correction
        since = now - window - timedelta(days=correction.days if correction else 0)
    entries = rt.bronze.log.list(rt.target_id, since=since)
    by_id: dict[str, CaptureEntry] = {e.capture_id: e for e in entries}
    latest_by_instant: dict[datetime, CaptureEntry] = {}
    for entry in entries:
        latest_by_instant[entry.scheduled_for] = entry  # ordered by attempt: last wins
    touched: list[Run] = []
    for scheduled_for, entry in latest_by_instant.items():
        before = rt.store.get_run(rt.target_id, scheduled_for)
        after = rt.store.ensure_run(
            rt.target_id,
            scheduled_for,
            state="captured",
            origin="reconciled",
            capture_id=entry.capture_id,
            now=now,
        )
        if (
            after.capture_id is not None
            and after.capture_id != entry.capture_id
            and _attempt_of(entry.capture_id) > _attempt_of(after.capture_id)
        ):
            known = by_id.get(after.capture_id) or rt.bronze.log.get(after.capture_id)
            if known is None or known.payload_sha256 != entry.payload_sha256:
                after = rt.store.mark_recaptured(after.id, entry.capture_id, now=now)
        if before is None or before.state != after.state or before.capture_id != after.capture_id:
            touched.append(after)
    return tuple(touched)
