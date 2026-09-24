"""``process``: reconcile → claim → read Bronze → decode → parse → map → fenced commit.

Every Silver write for a run and its state transition happen in ``store.commit`` under the
claim's fence (ADR-024 §4). A quarantined document (01 §9) commits no rows, one
``quarantine`` event, outcome ``quarantined`` and state ``failed``; Bronze keeps the payload
for replay after the fix.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import get_args

from energy_platform.bronze import BronzeError
from energy_platform.contracts.manifest import Manifest
from energy_platform.contracts.observation import EnergyObservation
from energy_platform.contracts.parser import DecodedDocument, SourceRecord
from energy_platform.contracts.registry import Transport, dataset
from energy_platform.mapping import (
    MappingContext,
    MappingResult,
    QualityEvent,
    Quarantined,
    map_records,
    partition_status,
    reconcile_transports,
)
from energy_platform.mapping.reconcile import CompareKey, compare_key
from energy_platform.parse import DecodeError, ParseError, decode, generic_parser, parser_ref
from energy_platform.parse.decode import decode_html_table
from energy_platform.runtime.context import Runtime, delivery_day_for
from energy_platform.runtime.reconcile import reconcile
from energy_platform.store import AttemptOutcome, Claim, Derivation, derivation_for

log = logging.getLogger("energy_platform.runtime")


@dataclass(frozen=True, slots=True)
class ProcessReport:
    run_id: int
    scheduled_for: datetime
    attempt_kind: str
    outcome: AttemptOutcome
    inserted: int = 0
    events: int = 0
    error: str | None = None


def process(rt: Runtime, *, limit: int | None = None) -> tuple[ProcessReport, ...]:
    """One ``process`` run: reconcile the window, then claim and process every pending run."""
    now = rt.clock()
    reconcile(rt, window=rt.reconcile_window, now=now)
    derivation = derivation_for(rt.manifest, parser_ref(rt.manifest))
    reports: list[ProcessReport] = []
    for run in rt.store.pending_runs(rt.target_id):
        if limit is not None and len(reports) >= limit:
            break
        claim = rt.store.claim(run.id, rt.owner, rt.lease_ttl, now=rt.clock())
        if claim is None:
            log.info("%s %s: held by another worker", rt.target_id, run.scheduled_for)
            continue
        reports.append(process_one(rt, claim, derivation))
    return tuple(reports)


def process_one(rt: Runtime, claim: Claim, derivation: Derivation) -> ProcessReport:
    run = claim.run
    capture_id = claim.attempt.capture_id or run.capture_id
    entry = None if capture_id is None else rt.bronze.log.get(capture_id)
    if entry is None:
        return _fail(rt, claim, derivation, f"capture entry {capture_id!r} not found in Bronze")
    try:
        payload = rt.bronze.read(entry.raw_ref).payload
    except BronzeError as exc:
        return _fail(rt, claim, derivation, str(exc))

    ctx = MappingContext(
        target_id=rt.target_id,
        scheduled_for=run.scheduled_for,
        delivery_day=delivery_day_for(run.scheduled_for, rt.timezone),
        fetched_at=entry.fetched_at,
        raw_ref=entry.raw_ref,
        payload_sha256=entry.payload_sha256,
        processed_at=rt.clock(),
        derivation_id=derivation.derivation_id,
    )
    try:
        result = map_payload(rt.manifest, payload, ctx)
    except Quarantined as q:
        log.warning("%s %s: quarantined: %s", rt.target_id, run.scheduled_for, q)
        commit = rt.store.commit(
            claim,
            state="failed",
            outcome="quarantined",
            error=q.reason,
            derivation=derivation,
            events=[q.as_event()],
            now=rt.clock(),
        )
        outcome: AttemptOutcome = "lost_lease" if commit.lost_lease else "quarantined"
        return ProcessReport(run.id, run.scheduled_for, claim.attempt.kind, outcome, 0, 1, q.reason)

    events = list(result.events)
    events.extend(completeness_events(result.observations, rt.timezone))
    events.extend(
        reconcile_transports(result.observations, _other_transport_rows(rt, result.observations))
    )
    commit = rt.store.commit(
        claim,
        state="processed",
        outcome="ok",
        derivation=derivation,
        observations=result.observations,
        events=events,
        now=rt.clock(),
    )
    if commit.lost_lease:
        return ProcessReport(run.id, run.scheduled_for, claim.attempt.kind, "lost_lease", 0, 0)
    outcome = "ok" if commit.inserted or not result.observations else "noop"
    return ProcessReport(
        run.id, run.scheduled_for, claim.attempt.kind, outcome, commit.inserted, len(events)
    )


def _fail(rt: Runtime, claim: Claim, derivation: Derivation, error: str) -> ProcessReport:
    log.error("%s %s: %s", rt.target_id, claim.run.scheduled_for, error)
    commit = rt.store.commit(
        claim,
        state="failed",
        outcome="failed",
        error=error,
        derivation=derivation,
        events=[QualityEvent("process_failed", "error", error)],
        now=rt.clock(),
    )
    outcome: AttemptOutcome = "lost_lease" if commit.lost_lease else "failed"
    return ProcessReport(
        claim.run.id, claim.run.scheduled_for, claim.attempt.kind, outcome, 0, 1, error
    )


def decode_payload(m: Manifest, payload: bytes) -> DecodedDocument:
    """Raw Bronze bytes → the decoded document the manifest declares (raises ``DecodeError``)."""
    if m.contract.decode == "html-table" and m.fetch.html_table is not None:
        return decode_html_table(payload, m.fetch.html_table.table_selector)
    return decode(payload, m.contract.decode)


def source_records(m: Manifest, payload: bytes) -> list[SourceRecord]:
    """Decode → generic parser: the source-shaped records production maps (raises
    ``DecodeError`` / ``ParseError``). The triage extractor reads the same documents (D-10)."""
    return list(generic_parser(m).parse(decode_payload(m, payload)))


def map_payload(m: Manifest, payload: bytes, ctx: MappingContext) -> MappingResult:
    """Decode → generic parser → mapping for one payload; raises ``Quarantined`` (01 §9).

    Shared by ``process`` and by the golden runner (``energy_platform.harness.goldens``), so a
    golden proves exactly what production would write.
    """
    try:
        records = source_records(m, payload)
    except (DecodeError, ParseError) as exc:
        raise Quarantined(f"{type(exc).__name__}: {exc}") from exc
    return map_records(m, records, ctx)


def completeness_events(
    observations: tuple[EnergyObservation, ...], timezone: str
) -> list[QualityEvent]:
    """01 §5 ``partition_status`` per resolution present in the document."""
    out: list[QualityEvent] = []
    for resolution in sorted({o.resolution for o in observations}):
        subset = [o for o in observations if o.resolution == resolution]
        out.extend(partition_status(subset, resolution, timezone))
    return out


def _other_transport_rows(
    rt: Runtime, observations: tuple[EnergyObservation, ...]
) -> dict[CompareKey, tuple[str, Decimal | None]]:
    """Each other transport's own current rows of the same dataset (01 §3 rule 2). Per
    transport, not the canonical view: the canonical row of an owned metric is the owner's
    (ADR-023 amendment 1), so the copy would never be seen there."""
    if not observations:
        return {}
    contract = dataset(rt.manifest.contract.dataset_id)
    if contract is None or not any(s.owner_transport for s in contract.metrics.values()):
        return {}
    mine = rt.manifest.contract.source_transport
    start = min(o.delivery_start_utc for o in observations)
    end = max(o.delivery_end_utc for o in observations)
    out: dict[CompareKey, tuple[str, Decimal | None]] = {}
    for other in get_args(Transport):
        if other == mine:
            continue
        for row in rt.store.current_rows(
            contract.dataset_id, start=start, end=end, transport=other
        ):
            out[compare_key(row.observation)] = (other, row.value)
    return out
