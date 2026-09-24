"""In-memory ``Store`` with the same semantics as Postgres: fencing, NULL-safe identity, view.

Used by unit tests, the ADR-023 proofs and the ADR-024 crash matrix. ``commit`` is all-or-
nothing: the fence is checked first and nothing is mutated when it is stale.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from datetime import datetime, timedelta

from energy_platform.contracts.observation import (
    EnergyObservation,
    observation_identity,
    version_identity,
)
from energy_platform.contracts.registry import Transport
from energy_platform.mapping.quality import QualityEvent
from energy_platform.store.ordering import ordering_basis, rank
from energy_platform.store.protocol import (
    AttemptKind,
    AttemptOutcome,
    Claim,
    CommitResult,
    CurrentRow,
    Derivation,
    Freshness,
    Run,
    RunAttempt,
    RunOrigin,
    RunState,
    StoredEvent,
    StoredObservation,
)

_FINAL: set[RunState] = {"processed"}


class MemoryStore:
    def __init__(self) -> None:
        self._runs: dict[int, Run] = {}
        self._attempts: dict[int, RunAttempt] = {}
        self._derivations: dict[str, Derivation] = {}
        self._rows: dict[int, StoredObservation] = {}
        self._events: dict[int, StoredEvent] = {}
        self._freshness: dict[str, Freshness] = {}
        self._seq = {"runs": 0, "attempts": 0, "rows": 0, "events": 0}

    def _next(self, table: str) -> int:
        self._seq[table] += 1
        return self._seq[table]

    # ---------------------------------------------------------------- runs

    def _find(self, target_id: str, scheduled_for: datetime) -> Run | None:
        for r in self._runs.values():
            if r.target_id == target_id and r.scheduled_for == scheduled_for:
                return r
        return None

    def ensure_run(
        self,
        target_id: str,
        scheduled_for: datetime,
        *,
        state: RunState,
        origin: RunOrigin,
        capture_id: str | None = None,
        now: datetime,
    ) -> Run:
        existing = self._find(target_id, scheduled_for)
        if existing is None:
            run = Run(
                id=self._next("runs"),
                target_id=target_id,
                scheduled_for=scheduled_for,
                state=state,
                fence=0,
                origin=origin,
                lease_owner=None,
                lease_until=None,
                capture_id=capture_id,
                created_at=now,
                updated_at=now,
            )
            self._runs[run.id] = run
            return run
        if state == "captured" and existing.state not in _FINAL and existing.capture_id is None:
            updated = replace(existing, state="captured", capture_id=capture_id, updated_at=now)
            self._runs[updated.id] = updated
            return updated
        return existing

    def get_run(self, target_id: str, scheduled_for: datetime) -> Run | None:
        return self._find(target_id, scheduled_for)

    def runs(
        self, target_id: str, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[Run, ...]:
        return tuple(
            sorted(
                (
                    r
                    for r in self._runs.values()
                    if r.target_id == target_id
                    and (since is None or r.scheduled_for >= since)
                    and (until is None or r.scheduled_for < until)
                ),
                key=lambda r: r.scheduled_for,
            )
        )

    def set_state(self, run_id: int, state: RunState, *, now: datetime) -> Run:
        run = replace(self._runs[run_id], state=state, updated_at=now)
        self._runs[run_id] = run
        return run

    def mark_recaptured(self, run_id: int, capture_id: str, *, now: datetime) -> Run:
        run = replace(self._runs[run_id], state="captured", capture_id=capture_id, updated_at=now)
        self._runs[run_id] = run
        return run

    # ---------------------------------------------------------------- attempts

    def claim(self, run_id: int, owner: str, ttl: timedelta, *, now: datetime) -> Claim | None:
        run = self._runs[run_id]
        if run.lease_until is not None and run.lease_until >= now:
            return None
        run = replace(
            run, fence=run.fence + 1, lease_owner=owner, lease_until=now + ttl, updated_at=now
        )
        self._runs[run_id] = run
        pending = next((a for a in self.attempts(run_id) if a.kind == "replay" and a.pending), None)
        if pending is not None:
            attempt = replace(
                pending,
                lease_owner=owner,
                lease_until=run.lease_until,
                fence=run.fence,
                capture_id=run.capture_id,
                started_at=now,
            )
        else:
            attempt = RunAttempt(
                id=self._next("attempts"),
                run_id=run_id,
                kind="process",
                lease_owner=owner,
                lease_until=run.lease_until,
                fence=run.fence,
                capture_id=run.capture_id,
                derivation_id=None,
                outcome=None,
                error=None,
                started_at=now,
                finished_at=None,
            )
        self._attempts[attempt.id] = attempt
        return Claim(run=run, fence=run.fence, attempt=attempt)

    def renew(self, claim: Claim, ttl: timedelta, *, now: datetime) -> bool:
        run = self._runs[claim.run.id]
        if run.fence != claim.fence:
            return False
        self._runs[run.id] = replace(run, lease_until=now + ttl, updated_at=now)
        return True

    def commit(
        self,
        claim: Claim,
        *,
        state: RunState,
        outcome: AttemptOutcome,
        error: str | None = None,
        derivation: Derivation | None = None,
        observations: Iterable[EnergyObservation] = (),
        events: Iterable[QualityEvent] = (),
        now: datetime,
    ) -> CommitResult:
        run = self._runs[claim.run.id]
        if run.fence != claim.fence:  # stale holder: nothing below happens
            stale = self._attempts[claim.attempt.id]
            if stale.outcome is None:
                self._attempts[stale.id] = replace(stale, outcome="lost_lease", finished_at=now)
            return CommitResult(inserted=0, lost_lease=True)
        if derivation is not None:
            self.register_derivation(derivation, now=now)
        existing = {version_identity(r.observation) for r in self._rows.values()}
        inserted = 0
        for o in observations:
            key = version_identity(o)
            if key in existing:
                continue
            existing.add(key)
            rid = self._next("rows")
            self._rows[rid] = StoredObservation(rid, claim.attempt.id, o)
            inserted += 1
        self.add_events(run.target_id, events, run_attempt_id=claim.attempt.id, now=now)
        attempt = self._attempts[claim.attempt.id]
        self._attempts[attempt.id] = replace(
            attempt,
            outcome=outcome,
            error=error,
            finished_at=now,
            derivation_id=None if derivation is None else derivation.derivation_id,
        )
        self._runs[run.id] = replace(
            run, state=state, lease_owner=None, lease_until=None, updated_at=now
        )
        return CommitResult(inserted=inserted, lost_lease=False)

    def record_attempt(
        self,
        run_id: int,
        kind: AttemptKind,
        *,
        outcome: AttemptOutcome,
        capture_id: str | None = None,
        error: str | None = None,
        now: datetime,
    ) -> RunAttempt:
        attempt = RunAttempt(
            id=self._next("attempts"),
            run_id=run_id,
            kind=kind,
            lease_owner=None,
            lease_until=None,
            fence=None,
            capture_id=capture_id,
            derivation_id=None,
            outcome=outcome,
            error=error,
            started_at=now,
            finished_at=now,
        )
        self._attempts[attempt.id] = attempt
        return attempt

    def enqueue_replay(self, run_id: int, *, now: datetime) -> RunAttempt | None:
        if any(a.kind == "replay" and a.pending for a in self.attempts(run_id)):
            return None
        attempt = RunAttempt(
            id=self._next("attempts"),
            run_id=run_id,
            kind="replay",
            lease_owner=None,
            lease_until=None,
            fence=None,
            capture_id=self._runs[run_id].capture_id,
            derivation_id=None,
            outcome=None,
            error=None,
            started_at=now,
            finished_at=None,
        )
        self._attempts[attempt.id] = attempt
        return attempt

    def attempts(self, run_id: int) -> tuple[RunAttempt, ...]:
        return tuple(a for a in self._attempts.values() if a.run_id == run_id)

    def pending_runs(self, target_id: str) -> tuple[Run, ...]:
        out = [
            r
            for r in self.runs(target_id)
            if r.state == "captured"
            or any(a.kind == "replay" and a.pending for a in self.attempts(r.id))
        ]
        return tuple(out)

    def runs_with_derivation(self, derivation_id: str) -> tuple[Run, ...]:
        attempt_ids = {
            r.run_attempt_id
            for r in self._rows.values()
            if r.observation.derivation_id == derivation_id
        }
        run_ids = {self._attempts[a].run_id for a in attempt_ids}
        return tuple(sorted((self._runs[i] for i in run_ids), key=lambda r: r.scheduled_for))

    # ---------------------------------------------------------------- derivations

    def register_derivation(self, d: Derivation, *, now: datetime) -> Derivation:
        stored = self._derivations.get(d.derivation_id)
        if stored is None:
            stored = replace(d, registered_at=now)
            self._derivations[d.derivation_id] = stored
        return stored

    def derivation(self, derivation_id: str) -> Derivation | None:
        return self._derivations.get(derivation_id)

    # ---------------------------------------------------------------- silver

    def _registered_at(self, derivation_id: str) -> datetime:
        d = self._derivations.get(derivation_id)
        if d is None or d.registered_at is None:
            raise KeyError(f"derivation {derivation_id} not registered")
        return d.registered_at

    def current_rows(
        self,
        dataset_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        metric: str | None = None,
        transport: Transport | None = None,
    ) -> tuple[CurrentRow, ...]:
        best: dict[tuple[object, ...], StoredObservation] = {}
        for row in self._rows.values():
            o = row.observation
            if o.dataset_id != dataset_id:
                continue
            if start is not None and o.delivery_start_utc < start:
                continue
            if end is not None and o.delivery_start_utc >= end:
                continue
            key = observation_identity(o)
            current = best.get(key)
            if current is None or rank(o, self._registered_at(o.derivation_id)) > rank(
                current.observation, self._registered_at(current.observation.derivation_id)
            ):
                best[key] = row
        rows = [
            CurrentRow(r.observation, r.run_attempt_id, ordering_basis(r.observation))
            for r in best.values()
            if (metric is None or r.observation.metric == metric)
            and (transport is None or r.observation.source_transport == transport)
        ]
        rows.sort(key=lambda c: (c.observation.delivery_start_utc, c.observation.metric))
        return tuple(rows)

    def all_rows(
        self, dataset_id: str, *, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[StoredObservation, ...]:
        return tuple(
            r
            for r in self._rows.values()
            if r.observation.dataset_id == dataset_id
            and (start is None or r.observation.delivery_start_utc >= start)
            and (end is None or r.observation.delivery_start_utc < end)
        )

    def iter_rows(
        self, dataset_id: str, *, transport: Transport | None = None
    ) -> Iterator[StoredObservation]:
        for rid in sorted(self._rows):
            r = self._rows[rid]
            o = r.observation
            if o.dataset_id != dataset_id:
                continue
            if transport is None or o.source_transport == transport:
                yield r

    def add_events(
        self,
        target_id: str,
        events: Iterable[QualityEvent],
        *,
        run_attempt_id: int | None,
        now: datetime,
    ) -> int:
        n = 0
        for e in events:
            eid = self._next("events")
            self._events[eid] = StoredEvent(
                eid,
                target_id,
                run_attempt_id,
                e.kind,
                e.severity,
                e.message,
                e.locator,
                e.metric,
                now,
            )
            n += 1
        return n

    def quality_events(
        self, target_id: str | None = None, *, kind: str | None = None
    ) -> tuple[StoredEvent, ...]:
        return tuple(
            e
            for e in self._events.values()
            if (target_id is None or e.target_id == target_id) and (kind is None or e.kind == kind)
        )

    # ---------------------------------------------------------------- freshness (ADR-037)

    def _delivered(
        self, dataset_id: str, transport: Transport | None
    ) -> Iterable[EnergyObservation]:
        for row in self._rows.values():
            o = row.observation
            if o.dataset_id != dataset_id or o.value is None:
                continue
            if transport is not None and o.source_transport != transport:
                continue
            yield o

    def count_periods(
        self, dataset_id: str, start: datetime, end: datetime, *, transport: Transport | None = None
    ) -> int:
        return len(
            {
                o.delivery_start_utc
                for o in self._delivered(dataset_id, transport)
                if start <= o.delivery_start_utc < end
            }
        )

    def newest_delivery_start(
        self, dataset_id: str, *, transport: Transport | None = None
    ) -> datetime | None:
        return max(
            (o.delivery_start_utc for o in self._delivered(dataset_id, transport)), default=None
        )

    def upsert_freshness(self, row: Freshness) -> None:
        self._freshness[row.target_id] = row

    def freshness_rows(self) -> tuple[Freshness, ...]:
        return tuple(self._freshness[k] for k in sorted(self._freshness))
