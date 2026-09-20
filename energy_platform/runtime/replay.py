"""``replay``: enqueue pending replay attempts; never fetches (ADR-004, ADR-023 §4, ADR-024 §5)."""

from __future__ import annotations

from datetime import datetime

from energy_platform.runtime.context import Runtime
from energy_platform.runtime.reconcile import reconcile
from energy_platform.store import RunAttempt


def replay_range(rt: Runtime, since: datetime, until: datetime) -> tuple[RunAttempt, ...]:
    """Enqueue a replay for every run in ``[since, until)`` that has a capture."""
    now = rt.clock()
    reconcile(rt, window=None, now=now)  # Bronze entries without a ledger row get one first
    queued: list[RunAttempt] = []
    for run in rt.store.runs(rt.target_id, since, until):
        if run.capture_id is None:
            continue
        attempt = rt.store.enqueue_replay(run.id, now=now)
        if attempt is not None:
            queued.append(attempt)
    return tuple(queued)


def replay_derivation(rt: Runtime, derivation_id: str) -> tuple[RunAttempt, ...]:
    """ADR-016 §4 repair: replay every capture that has a Silver row with ``derivation_id``."""
    now = rt.clock()
    queued: list[RunAttempt] = []
    for run in rt.store.runs_with_derivation(derivation_id):
        if run.target_id != rt.target_id:
            continue
        attempt = rt.store.enqueue_replay(run.id, now=now)
        if attempt is not None:
            queued.append(attempt)
    return tuple(queued)
