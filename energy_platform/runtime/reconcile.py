"""``reconcile``: Bronze is the truth, the ledger is rebuilt from it (ADR-024 §2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from energy_platform.runtime.context import Runtime
from energy_platform.store import Run


def reconcile(
    rt: Runtime, *, window: timedelta | None = None, now: datetime | None = None
) -> tuple[Run, ...]:
    """Insert missing ledger rows (``origin=reconciled``) for every capture-log entry in the
    window; returns the runs that were created or advanced to ``captured``."""
    now = now or rt.clock()
    since = None if window is None else now - window
    latest_by_instant = {}
    for entry in rt.bronze.log.list(rt.target_id, since=since):
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
        if before is None or before.state != after.state or before.capture_id != after.capture_id:
            touched.append(after)
    return tuple(touched)
