"""``capture`` and the fetching half of ``backfill``: FETCH → WRITE RAW → ACK → (ledger).

The ledger row is written last and best-effort (ADR-024 §1): a store outage is a warning, the
capture is complete once Bronze holds the blob and the entry. A failed fetch writes nothing to
Bronze and, best-effort, an attempt with outcome ``source_unavailable``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from energy_platform.bronze import BronzeError, CaptureEntry
from energy_platform.fetch import EgressError, FetchContext, FetchFailed, RenderError
from energy_platform.fetch.client import Conditional
from energy_platform.fetch.plan import fetch_for_manifest
from energy_platform.fetch.secrets import SecretMissing
from energy_platform.runtime.context import Runtime, delivery_day_for
from energy_platform.store import AttemptOutcome, RunOrigin, RunState, StoreUnavailable

log = logging.getLogger("energy_platform.runtime")

CaptureKind = Literal["capture", "backfill"]


@dataclass(frozen=True, slots=True)
class CaptureReport:
    scheduled_for: datetime
    outcome: AttemptOutcome
    entry: CaptureEntry | None = None
    created: bool = False
    error: str | None = None
    ledger_updated: bool = False


def capture(
    rt: Runtime,
    scheduled_for: datetime,
    *,
    delivery_day: date | None = None,
    force: bool = False,
    kind: CaptureKind = "capture",
) -> CaptureReport:
    target = rt.target_id
    origin: RunOrigin = "backfill" if kind == "backfill" else "scheduled"
    existing = rt.bronze.log.entries_for(target, scheduled_for)
    if existing and not force:
        entry = existing[-1]
        updated = _ack(rt, scheduled_for, origin, kind, "noop", entry.capture_id, None)
        return CaptureReport(scheduled_for, "noop", entry, False, None, updated)

    ctx = FetchContext.for_run(
        scheduled_for, delivery_day=delivery_day or delivery_day_for(scheduled_for, rt.timezone)
    )
    previous = rt.bronze.log.latest(target)
    conditional = None if previous is None else Conditional(previous.etag, previous.last_modified)
    try:
        result = fetch_for_manifest(
            rt.manifest,
            ctx,
            rt.fetcher_factory(rt.manifest),
            previous=conditional,
            secrets=rt.secrets,
        )
    except (FetchFailed, EgressError) as exc:
        log.warning("%s %s: source unavailable: %s", target, scheduled_for, exc)
        updated = _ack(rt, scheduled_for, origin, kind, "source_unavailable", None, str(exc))
        return CaptureReport(scheduled_for, "source_unavailable", None, False, str(exc), updated)
    except (RenderError, SecretMissing, LookupError) as exc:
        log.error("%s %s: cannot build the request: %s", target, scheduled_for, exc)
        updated = _ack(rt, scheduled_for, origin, kind, "failed", None, str(exc))
        return CaptureReport(scheduled_for, "failed", None, False, str(exc), updated)

    try:
        outcome = rt.bronze.capture(
            target_id=target,
            scheduled_for=scheduled_for,
            result=result,
            transport=rt.manifest.contract.source_transport,
            force=force,
        )
    except BronzeError as exc:
        log.error("%s %s: Bronze refused the capture: %s", target, scheduled_for, exc)
        updated = _ack(rt, scheduled_for, origin, kind, "failed", None, str(exc))
        return CaptureReport(scheduled_for, "failed", None, False, str(exc), updated)

    updated = _ack(rt, scheduled_for, origin, kind, "ok", outcome.entry.capture_id, None)
    return CaptureReport(scheduled_for, "ok", outcome.entry, outcome.created, None, updated)


def _ack(
    rt: Runtime,
    scheduled_for: datetime,
    origin: RunOrigin,
    kind: CaptureKind,
    outcome: AttemptOutcome,
    capture_id: str | None,
    error: str | None,
) -> bool:
    """Ledger bookkeeping after Bronze; a store outage never fails the capture (ADR-024 §1)."""
    now = rt.clock()
    try:
        state: RunState = "captured" if capture_id is not None else "scheduled"
        run = rt.store.ensure_run(
            rt.target_id, scheduled_for, state=state, origin=origin, capture_id=capture_id, now=now
        )
        if outcome != "noop":
            rt.store.record_attempt(
                run.id, kind, outcome=outcome, capture_id=capture_id, error=error, now=now
            )
    except StoreUnavailable as exc:
        log.warning(
            "%s %s: ledger unavailable, reconcile later: %s", rt.target_id, scheduled_for, exc
        )
        return False
    return True
