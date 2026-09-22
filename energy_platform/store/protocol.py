"""The ``Store`` protocol and its row types (ADR-003 rev., ADR-018, ADR-023, ADR-024).

Rows are frozen dataclasses mirroring the tables created by the migrations:

* ``runs`` — one per ``(target_id, scheduled_for)``: ``state``, ``fence``, ``origin``, latest
  lease, ``capture_id`` of the capture that completed it;
* ``run_attempts`` — one per attempt: ``kind``, lease, ``fence``, ``capture_id``,
  ``derivation_id``, ``outcome``, ``error``;
* ``derivations`` — the ADR-023 §1 components behind a ``derivation_id``;
* ``observations`` — ``EnergyObservation`` plus ``run_attempt_id``; version identity unique;
* ``quality_events`` — data, never exceptions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol

import energy_platform
from energy_platform.contracts.manifest import Manifest
from energy_platform.contracts.observation import EnergyObservation, derivation_id
from energy_platform.contracts.registry import Transport, dataset
from energy_platform.mapping.quality import QualityEvent

RunState = Literal[
    "scheduled", "captured", "processed", "failed", "missing_capture", "unrecoverable"
]
RunOrigin = Literal["scheduled", "reconciled", "backfill", "replay", "manual"]
AttemptKind = Literal["capture", "process", "backfill", "replay"]
AttemptOutcome = Literal["ok", "failed", "lost_lease", "quarantined", "noop", "source_unavailable"]


class StoreUnavailable(Exception):
    """The database cannot be reached or is not what ADR-030 requires."""


@dataclass(frozen=True, slots=True)
class Run:
    id: int
    target_id: str
    scheduled_for: datetime
    state: RunState
    fence: int
    origin: RunOrigin
    lease_owner: str | None
    lease_until: datetime | None
    capture_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RunAttempt:
    id: int
    run_id: int
    kind: AttemptKind
    lease_owner: str | None
    lease_until: datetime | None
    fence: int | None
    capture_id: str | None
    derivation_id: str | None
    outcome: AttemptOutcome | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None

    @property
    def pending(self) -> bool:
        return self.outcome is None and self.lease_owner is None


@dataclass(frozen=True, slots=True)
class Derivation:
    derivation_id: str
    platform_version: str
    contract_version: str
    mapping_block: Mapping[str, Any]
    parser_ref: str
    registered_at: datetime | None = None


def derivation_for(manifest: Manifest, parser_ref: str) -> Derivation:
    """ADR-023 §1 components for this manifest under the running platform version."""
    contract = dataset(manifest.contract.dataset_id)
    if contract is None:
        raise ValueError(f"{manifest.contract.dataset_id!r} is not registered")
    block = manifest.mapping_block()
    return Derivation(
        derivation_id=derivation_id(
            energy_platform.__version__, contract.contract_version, block, parser_ref
        ),
        platform_version=energy_platform.__version__,
        contract_version=contract.contract_version,
        mapping_block=block,
        parser_ref=parser_ref,
    )


@dataclass(frozen=True, slots=True)
class Claim:
    run: Run
    fence: int
    attempt: RunAttempt


@dataclass(frozen=True, slots=True)
class CommitResult:
    inserted: int
    lost_lease: bool


@dataclass(frozen=True, slots=True)
class StoredObservation:
    id: int
    run_attempt_id: int
    observation: EnergyObservation


@dataclass(frozen=True, slots=True)
class CurrentRow:
    """One row of the current view (ADR-023 §3): the observation plus how it won."""

    observation: EnergyObservation
    run_attempt_id: int
    ordering_basis: Literal["source_published_at", "fetched_at"]

    @property
    def value(self) -> Decimal | None:
        return self.observation.value


@dataclass(frozen=True, slots=True)
class StoredEvent:
    id: int
    target_id: str
    run_attempt_id: int | None
    kind: str
    severity: str
    message: str
    locator: str
    metric: str | None
    created_at: datetime


class Store(Protocol):
    # ---------------------------------------------------------------- ledger: runs
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
        """Insert the run if absent. If present and ``state`` is ``captured``, record the
        capture (state and ``capture_id``) unless the run is already past it. Never lowers a
        ``processed`` run."""
        ...

    def get_run(self, target_id: str, scheduled_for: datetime) -> Run | None: ...

    def runs(
        self, target_id: str, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[Run, ...]: ...

    def set_state(self, run_id: int, state: RunState, *, now: datetime) -> Run:
        """Unfenced transition used only by the gap detector for ``missing_capture`` /
        ``unrecoverable`` (runs that nobody holds)."""
        ...

    def mark_recaptured(self, run_id: int, capture_id: str, *, now: datetime) -> Run:
        """ADR-033 §3: a forced re-capture whose payload changed makes the run pending again —
        ``state = captured`` and ``capture_id`` pointing at the new attempt, whatever the state
        was (a ``processed`` run is lowered on purpose: the new content must be processed)."""
        ...

    # ---------------------------------------------------------------- ledger: attempts
    def claim(self, run_id: int, owner: str, ttl: timedelta, *, now: datetime) -> Claim | None:
        """ADR-024 §4: bump the fence and take the lease if it is free or expired; adopt a
        pending replay attempt if one exists, else open a ``process`` attempt."""
        ...

    def renew(self, claim: Claim, ttl: timedelta, *, now: datetime) -> bool: ...

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
        """One transaction predicated on ``runs.fence = claim.fence``: register the
        derivation, insert the rows (version identity conflicts insert nothing), insert the
        events, close the attempt, set the state and release the lease. A stale fence changes
        nothing and returns ``lost_lease=True``."""
        ...

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
        """Unleased attempt bookkeeping for ``capture`` / ``backfill`` (Bronze is their lock)."""
        ...

    def enqueue_replay(self, run_id: int, *, now: datetime) -> RunAttempt | None:
        """Add a pending ``replay`` attempt unless one is already pending (P2-D11)."""
        ...

    def attempts(self, run_id: int) -> tuple[RunAttempt, ...]: ...

    def pending_runs(self, target_id: str) -> tuple[Run, ...]:
        """Runs to process: ``state = captured`` or with a pending replay attempt (P2-D11)."""
        ...

    def runs_with_derivation(self, derivation_id: str) -> tuple[Run, ...]:
        """Runs whose Silver rows carry ``derivation_id`` (ADR-023 §4 repair)."""
        ...

    # ---------------------------------------------------------------- derivations
    def register_derivation(self, d: Derivation, *, now: datetime) -> Derivation: ...

    def derivation(self, derivation_id: str) -> Derivation | None: ...

    # ---------------------------------------------------------------- silver
    def current_rows(
        self,
        dataset_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        metric: str | None = None,
        transport: Transport | None = None,
    ) -> tuple[CurrentRow, ...]: ...

    def all_rows(
        self, dataset_id: str, *, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[StoredObservation, ...]: ...

    def add_events(
        self,
        target_id: str,
        events: Iterable[QualityEvent],
        *,
        run_attempt_id: int | None,
        now: datetime,
    ) -> int: ...

    def quality_events(
        self, target_id: str | None = None, *, kind: str | None = None
    ) -> tuple[StoredEvent, ...]: ...
