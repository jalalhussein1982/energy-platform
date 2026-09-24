"""``Store`` over plain PostgreSQL >= 16 with psycopg 3 (ADR-030).

Every method is one transaction. ``commit`` locks the run row with ``FOR UPDATE`` under the
fence predicate (ADR-024 §4): a stale holder finds zero rows, rolls back and is recorded as
``lost_lease``; a concurrent claimer blocks until the holder's transaction ends and then sees
the new state. The current view is ``observations_current`` from migration 0002.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timedelta
from typing import Any, cast

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from energy_platform.contracts.intervals import DeliveryInterval
from energy_platform.contracts.invalidation import Invalidation
from energy_platform.contracts.observation import EnergyObservation
from energy_platform.contracts.registry import Transport
from energy_platform.mapping.quality import QualityEvent
from energy_platform.store.ordering import owner_transport_of
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
    StoreUnavailable,
)

MIN_SERVER_VERSION = 160000  # ADR-030
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _schema_name(name: str) -> str:
    """A schema name safe to interpolate into ``search_path`` (no quoting available there)."""
    if not _SCHEMA_NAME.match(name):
        raise ValueError(f"{name!r} is not a plain lowercase schema name")
    return name


_OBS_COLUMNS = (
    "source_id, dataset_id, source_transport, contract_version, derivation_id, raw_ref, "
    "payload_sha256, fetched_at, source_published_at, source_version, processed_at, "
    "delivery_interval, resolution, local_date, period_index, kind, dimensions, metric, value, "
    "unit, sign_convention, run_attempt_id, owner_transport"
)
_INSERT_OBSERVATION = sql.SQL(
    "INSERT INTO observations ({cols}) VALUES ("
    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, tstzrange(%s, %s, '[)'), "
    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    # the version-identity index (0002); a conflict returns the existing row's id (xmax <> 0)
    "ON CONFLICT (dataset_id, dimensions, delivery_start_utc, resolution, metric, "
    "source_version, payload_sha256, derivation_id) "
    "DO UPDATE SET run_attempt_id = observations.run_attempt_id "
    "RETURNING id, (xmax = 0) AS inserted"
).format(cols=sql.SQL(_OBS_COLUMNS))
_INSERT_OCCURRENCE = (
    "INSERT INTO observation_occurrences (observation_id, run_attempt_id, fetched_at, "
    "source_published_at) VALUES (%s, %s, %s, %s) ON CONFLICT (observation_id, fetched_at) "
    "DO NOTHING"
)
_OBS_SELECT = (
    "id, run_attempt_id, source_id, dataset_id, source_transport, contract_version, "
    "derivation_id, raw_ref, payload_sha256, fetched_at, source_published_at, source_version, "
    "processed_at, lower(delivery_interval) AS delivery_start, upper(delivery_interval) AS "
    "delivery_end, resolution, local_date, period_index, kind, dimensions, metric, value, unit, "
    "sign_convention"
)


class PostgresStore:
    def __init__(self, dsn: str, *, schema: str | None = None) -> None:
        """``schema`` scopes every statement to one schema (``search_path``); the smoke hook
        uses a throwaway schema so synthetic fixture rows never reach the real tables."""
        self._dsn = dsn
        options = "-c timezone=UTC"
        if schema is not None:
            options += f" -c search_path={_schema_name(schema)}"
        try:
            self._conn = psycopg.connect(
                dsn, row_factory=dict_row, autocommit=False, options=options
            )
        except psycopg.OperationalError as exc:
            raise StoreUnavailable(f"cannot connect: {exc}") from exc
        with self._conn.cursor() as cur:
            cur.execute("SELECT current_setting('server_version_num')::int AS v")
            row = cur.fetchone()
        self._conn.rollback()
        version = int(row["v"]) if row else 0
        if version < MIN_SERVER_VERSION:
            self._conn.close()
            raise StoreUnavailable(
                f"PostgreSQL server_version_num {version} < {MIN_SERVER_VERSION} (ADR-030)"
            )

    def close(self) -> None:
        self._conn.close()

    # ---------------------------------------------------------------- helpers

    def _one(self, query: str | sql.Composed, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        return None if row is None else dict(row)

    def _all(self, query: str | sql.Composed, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def _run(r: dict[str, Any]) -> Run:
        return Run(
            id=r["id"],
            target_id=r["target_id"],
            scheduled_for=r["scheduled_for"],
            state=r["state"],
            fence=r["fence"],
            origin=r["origin"],
            lease_owner=r["lease_owner"],
            lease_until=r["lease_until"],
            capture_id=r["capture_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    @staticmethod
    def _attempt(r: dict[str, Any]) -> RunAttempt:
        return RunAttempt(
            id=r["id"],
            run_id=r["run_id"],
            kind=r["kind"],
            lease_owner=r["lease_owner"],
            lease_until=r["lease_until"],
            fence=r["fence"],
            capture_id=r["capture_id"],
            derivation_id=r["derivation_id"],
            outcome=r["outcome"],
            error=r["error"],
            started_at=r["started_at"],
            finished_at=r["finished_at"],
        )

    @staticmethod
    def _observation(r: dict[str, Any]) -> EnergyObservation:
        return EnergyObservation(
            source_id=r["source_id"],
            dataset_id=r["dataset_id"],
            source_transport=r["source_transport"],
            contract_version=r["contract_version"],
            derivation_id=r["derivation_id"],
            raw_ref=r["raw_ref"],
            payload_sha256=r["payload_sha256"],
            fetched_at=r["fetched_at"],
            source_published_at=r["source_published_at"],
            source_version=r["source_version"],
            processed_at=r["processed_at"],
            delivery_interval=DeliveryInterval(r["delivery_start"], r["delivery_end"]),
            resolution=r["resolution"],
            local_date=r["local_date"],
            period_index=r["period_index"],
            kind=r["kind"],
            dimensions=dict(r["dimensions"]),
            metric=r["metric"],
            value=r["value"],
            unit=r["unit"],
            sign_convention=r["sign_convention"],
        )

    @staticmethod
    def _event(r: dict[str, Any]) -> StoredEvent:
        return StoredEvent(
            r["id"],
            r["target_id"],
            r["run_attempt_id"],
            r["kind"],
            r["severity"],
            r["message"],
            r["locator"],
            r["metric"],
            r["created_at"],
        )

    # ---------------------------------------------------------------- runs

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
        try:
            row = self._one(
                """
                INSERT INTO runs (target_id, scheduled_for, state, origin, capture_id,
                                  created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (target_id, scheduled_for) DO UPDATE SET
                    state = CASE WHEN EXCLUDED.state = 'captured' AND runs.state <> 'processed'
                                      AND runs.capture_id IS NULL
                                 THEN 'captured' ELSE runs.state END,
                    capture_id = CASE WHEN EXCLUDED.state = 'captured' AND runs.state <> 'processed'
                                           AND runs.capture_id IS NULL
                                      THEN EXCLUDED.capture_id ELSE runs.capture_id END,
                    updated_at = CASE WHEN EXCLUDED.state = 'captured' AND runs.state <> 'processed'
                                           AND runs.capture_id IS NULL
                                      THEN EXCLUDED.updated_at ELSE runs.updated_at END
                RETURNING *
                """,
                (target_id, scheduled_for, state, origin, capture_id, now, now),
            )
            self._conn.commit()
        except psycopg.OperationalError as exc:
            self._conn.rollback()
            raise StoreUnavailable(str(exc)) from exc
        if row is None:
            raise StoreUnavailable("ensure_run returned no row")
        return self._run(row)

    def get_run(self, target_id: str, scheduled_for: datetime) -> Run | None:
        row = self._one(
            "SELECT * FROM runs WHERE target_id = %s AND scheduled_for = %s",
            (target_id, scheduled_for),
        )
        self._conn.rollback()
        return None if row is None else self._run(row)

    def runs(
        self, target_id: str, since: datetime | None = None, until: datetime | None = None
    ) -> tuple[Run, ...]:
        rows = self._all(
            """
            SELECT * FROM runs
            WHERE target_id = %s
              AND (%s::timestamptz IS NULL OR scheduled_for >= %s)
              AND (%s::timestamptz IS NULL OR scheduled_for < %s)
            ORDER BY scheduled_for
            """,
            (target_id, since, since, until, until),
        )
        self._conn.rollback()
        return tuple(self._run(r) for r in rows)

    def set_state(self, run_id: int, state: RunState, *, now: datetime) -> Run:
        row = self._one(
            "UPDATE runs SET state = %s, updated_at = %s WHERE id = %s RETURNING *",
            (state, now, run_id),
        )
        self._conn.commit()
        if row is None:
            raise KeyError(f"run {run_id} does not exist")
        return self._run(row)

    def mark_recaptured(self, run_id: int, capture_id: str, *, now: datetime) -> Run:
        # ADR-024 amendment 1: a new generation invalidates any in-flight claim (fence + 1)
        row = self._one(
            "UPDATE runs SET state = 'captured', capture_id = %s, fence = fence + 1, "
            "lease_owner = NULL, lease_until = NULL, updated_at = %s "
            "WHERE id = %s RETURNING *",
            (capture_id, now, run_id),
        )
        self._conn.commit()
        if row is None:
            raise KeyError(f"run {run_id} does not exist")
        return self._run(row)

    # ---------------------------------------------------------------- attempts

    def claim(self, run_id: int, owner: str, ttl: timedelta, *, now: datetime) -> Claim | None:
        row = self._one(
            """
            UPDATE runs SET fence = fence + 1, lease_owner = %s, lease_until = %s, updated_at = %s
            WHERE id = %s AND (lease_until IS NULL OR lease_until < %s)
            RETURNING *
            """,
            (owner, now + ttl, now, run_id, now),
        )
        if row is None:
            self._conn.rollback()
            return None
        run = self._run(row)
        # ADR-024 amendment 2: close replay attempts abandoned by a dead worker, reopen one
        dead = self._all(
            """
            UPDATE run_attempts SET outcome = 'lost_lease', finished_at = %s
            WHERE run_id = %s AND kind = 'replay' AND outcome IS NULL
              AND lease_owner IS NOT NULL AND lease_until < %s
            RETURNING id
            """,
            (now, run_id, now),
        )
        if dead:
            self._one(
                """
                INSERT INTO run_attempts (run_id, kind, capture_id, started_at)
                SELECT %s, 'replay', %s, %s WHERE NOT EXISTS (
                    SELECT 1 FROM run_attempts a
                    WHERE a.run_id = %s AND a.kind = 'replay' AND a.outcome IS NULL
                      AND a.lease_owner IS NULL)
                RETURNING id
                """,
                (run_id, run.capture_id, now, run_id),
            )
        pending = self._one(
            """
            UPDATE run_attempts SET lease_owner = %s, lease_until = %s, fence = %s,
                                    capture_id = %s, started_at = %s
            WHERE id = (SELECT id FROM run_attempts
                        WHERE run_id = %s AND kind = 'replay' AND outcome IS NULL
                          AND lease_owner IS NULL
                        ORDER BY id LIMIT 1)
            RETURNING *
            """,
            (owner, run.lease_until, run.fence, run.capture_id, now, run_id),
        )
        if pending is None:
            pending = self._one(
                """
                INSERT INTO run_attempts (run_id, kind, lease_owner, lease_until, fence,
                                          capture_id, started_at)
                VALUES (%s, 'process', %s, %s, %s, %s, %s) RETURNING *
                """,
                (run_id, owner, run.lease_until, run.fence, run.capture_id, now),
            )
        self._conn.commit()
        if pending is None:
            raise StoreUnavailable("claim: attempt row missing")
        return Claim(run=run, fence=run.fence, attempt=self._attempt(pending))

    def renew(self, claim: Claim, ttl: timedelta, *, now: datetime) -> bool:
        row = self._one(
            "UPDATE runs SET lease_until = %s, updated_at = %s WHERE id = %s AND fence = %s "
            "RETURNING id",
            (now + ttl, now, claim.run.id, claim.fence),
        )
        self._conn.commit()
        return row is not None

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
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM runs WHERE id = %s AND fence = %s FOR UPDATE",
                (claim.run.id, claim.fence),
            )
            if cur.fetchone() is None:
                self._conn.rollback()
                cur.execute(
                    "UPDATE run_attempts SET outcome = 'lost_lease', finished_at = %s "
                    "WHERE id = %s AND outcome IS NULL",
                    (now, claim.attempt.id),
                )
                self._conn.commit()
                return CommitResult(inserted=0, lost_lease=True)
            if derivation is not None:
                self._insert_derivation(cur, derivation, now)
            inserted = 0
            occurrences = 0
            for o in observations:
                cur.execute(
                    _INSERT_OBSERVATION,
                    (
                        o.source_id,
                        o.dataset_id,
                        o.source_transport,
                        o.contract_version,
                        o.derivation_id,
                        o.raw_ref,
                        o.payload_sha256,
                        o.fetched_at,
                        o.source_published_at,
                        o.source_version,
                        o.processed_at,
                        o.delivery_start_utc,
                        o.delivery_end_utc,
                        o.resolution,
                        o.local_date,
                        o.period_index,
                        o.kind,
                        Jsonb(dict(o.dimensions)),
                        o.metric,
                        o.value,
                        o.unit,
                        o.sign_convention,
                        claim.attempt.id,
                        owner_transport_of(o),  # ADR-023 amendment 1: from the registry
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise StoreUnavailable("observation insert returned no row")
                new_version = bool(row["inserted"])
                inserted += int(new_version)
                # ADR-023 amendment 2: every capture that produced this version is an
                # occurrence; the same capture again (same fetched_at) is not
                cur.execute(
                    _INSERT_OCCURRENCE,
                    (row["id"], claim.attempt.id, o.fetched_at, o.source_published_at),
                )
                if cur.rowcount and not new_version:
                    occurrences += 1
            self._insert_events(cur, claim.run.target_id, events, claim.attempt.id, now)
            cur.execute(
                "UPDATE run_attempts SET outcome = %s, error = %s, finished_at = %s, "
                "derivation_id = %s WHERE id = %s",
                (
                    outcome,
                    error,
                    now,
                    None if derivation is None else derivation.derivation_id,
                    claim.attempt.id,
                ),
            )
            cur.execute(
                "UPDATE runs SET state = %s, lease_owner = NULL, lease_until = NULL, "
                "updated_at = %s WHERE id = %s AND fence = %s",
                (state, now, claim.run.id, claim.fence),
            )
        self._conn.commit()
        return CommitResult(inserted=inserted, lost_lease=False, occurrences=occurrences)

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
        row = self._one(
            """
            INSERT INTO run_attempts (run_id, kind, capture_id, outcome, error, started_at,
                                      finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *
            """,
            (run_id, kind, capture_id, outcome, error, now, now),
        )
        self._conn.commit()
        if row is None:
            raise StoreUnavailable("record_attempt returned no row")
        return self._attempt(row)

    def enqueue_replay(self, run_id: int, *, now: datetime) -> RunAttempt | None:
        row = self._one(
            """
            INSERT INTO run_attempts (run_id, kind, capture_id, started_at)
            SELECT r.id, 'replay', r.capture_id, %s FROM runs r
            WHERE r.id = %s AND NOT EXISTS (
                SELECT 1 FROM run_attempts a
                WHERE a.run_id = r.id AND a.kind = 'replay' AND a.outcome IS NULL
                  AND a.lease_owner IS NULL)
            RETURNING *
            """,
            (now, run_id),
        )
        self._conn.commit()
        return None if row is None else self._attempt(row)

    def attempts(self, run_id: int) -> tuple[RunAttempt, ...]:
        rows = self._all("SELECT * FROM run_attempts WHERE run_id = %s ORDER BY id", (run_id,))
        self._conn.rollback()
        return tuple(self._attempt(r) for r in rows)

    def pending_runs(self, target_id: str, *, now: datetime) -> tuple[Run, ...]:
        rows = self._all(
            """
            SELECT r.* FROM runs r
            WHERE r.target_id = %s AND (
                r.state = 'captured' OR EXISTS (
                    SELECT 1 FROM run_attempts a
                    WHERE a.run_id = r.id AND a.kind = 'replay' AND a.outcome IS NULL
                      AND (a.lease_owner IS NULL OR a.lease_until < %s)))
            ORDER BY r.scheduled_for
            """,
            (target_id, now),
        )
        self._conn.rollback()
        return tuple(self._run(r) for r in rows)

    def runs_with_derivation(self, derivation_id: str) -> tuple[Run, ...]:
        rows = self._all(
            """
            SELECT DISTINCT r.* FROM runs r
            JOIN run_attempts a ON a.run_id = r.id
            JOIN observations o ON o.run_attempt_id = a.id
            WHERE o.derivation_id = %s
            ORDER BY r.scheduled_for
            """,
            (derivation_id,),
        )
        self._conn.rollback()
        return tuple(self._run(r) for r in rows)

    # ---------------------------------------------------------------- invalidations (ADR-038)

    def add_invalidation(self, inv: Invalidation) -> bool:
        row = self._one(
            """
            INSERT INTO invalidations (target_id, capture_id, derivation_id, reason, recorded_by,
                                       recorded_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (target_id, capture_id, derivation_id) DO NOTHING
            RETURNING id
            """,
            (
                inv.target_id,
                inv.capture_id,
                inv.derivation_id,
                inv.reason,
                inv.recorded_by,
                inv.recorded_at,
            ),
        )
        self._conn.commit()
        return row is not None

    def invalidations(self, target_id: str) -> tuple[Invalidation, ...]:
        rows = self._all(
            "SELECT * FROM invalidations WHERE target_id = %s ORDER BY capture_id, derivation_id",
            (target_id,),
        )
        self._conn.rollback()
        return tuple(
            Invalidation(
                target_id=r["target_id"],
                capture_id=r["capture_id"],
                derivation_id=r["derivation_id"],
                reason=r["reason"],
                recorded_by=r["recorded_by"],
                recorded_at=r["recorded_at"],
            )
            for r in rows
        )

    def is_invalidated(self, capture_id: str, derivation_id: str | None) -> bool:
        row = self._one(
            """
            SELECT 1 AS hit FROM invalidations
            WHERE capture_id = %s AND (derivation_id IS NULL OR derivation_id = %s)
            LIMIT 1
            """,
            (capture_id, derivation_id),
        )
        self._conn.rollback()
        return row is not None

    def attempt_captures(self, target_id: str) -> Mapping[int, str]:
        rows = self._all(
            """
            SELECT a.id, a.capture_id FROM run_attempts a
            JOIN runs r ON r.id = a.run_id
            WHERE r.target_id = %s AND a.capture_id IS NOT NULL
            """,
            (target_id,),
        )
        self._conn.rollback()
        return {int(r["id"]): str(r["capture_id"]) for r in rows}

    # ---------------------------------------------------------------- derivations

    def _insert_derivation(self, cur: psycopg.Cursor[Any], d: Derivation, now: datetime) -> None:
        cur.execute(
            """
            INSERT INTO derivations (derivation_id, platform_version, contract_version,
                                     mapping_block, parser_ref, registered_at)
            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (derivation_id) DO NOTHING
            """,
            (
                d.derivation_id,
                d.platform_version,
                d.contract_version,
                Jsonb(json.loads(json.dumps(d.mapping_block))),
                d.parser_ref,
                now,
            ),
        )

    def register_derivation(self, d: Derivation, *, now: datetime) -> Derivation:
        with self._conn.cursor() as cur:
            self._insert_derivation(cur, d, now)
        self._conn.commit()
        stored = self.derivation(d.derivation_id)
        if stored is None:
            raise StoreUnavailable("derivation vanished after insert")
        return stored

    def derivation(self, derivation_id: str) -> Derivation | None:
        row = self._one("SELECT * FROM derivations WHERE derivation_id = %s", (derivation_id,))
        self._conn.rollback()
        if row is None:
            return None
        return Derivation(
            derivation_id=row["derivation_id"],
            platform_version=row["platform_version"],
            contract_version=row["contract_version"],
            mapping_block=dict(row["mapping_block"]),
            parser_ref=row["parser_ref"],
            registered_at=row["registered_at"],
        )

    # ---------------------------------------------------------------- silver

    def current_rows(
        self,
        dataset_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        metric: str | None = None,
        transport: Transport | None = None,
    ) -> tuple[CurrentRow, ...]:
        # ADR-023 amendment 1: no transport → the canonical view (owner first); a transport →
        # that transport's own current row (the reconciliation copy stays selectable)
        view = "observations_current" if transport is None else "observations_current_by_transport"
        rows = self._all(
            sql.SQL(
                """
            SELECT {cols}, ordering_basis FROM {view}
            WHERE dataset_id = %s
              AND (%s::timestamptz IS NULL OR lower(delivery_interval) >= %s)
              AND (%s::timestamptz IS NULL OR lower(delivery_interval) < %s)
              AND (%s::text IS NULL OR metric = %s)
              AND (%s::text IS NULL OR source_transport = %s)
            ORDER BY lower(delivery_interval), metric
            """
            ).format(cols=sql.SQL(_OBS_SELECT), view=sql.Identifier(view)),
            (dataset_id, start, start, end, end, metric, metric, transport, transport),
        )
        self._conn.rollback()
        return tuple(
            CurrentRow(self._observation(r), r["run_attempt_id"], r["ordering_basis"]) for r in rows
        )

    def all_rows(
        self, dataset_id: str, *, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[StoredObservation, ...]:
        rows = self._all(
            sql.SQL(
                """
            SELECT {cols} FROM observations
            WHERE dataset_id = %s
              AND (%s::timestamptz IS NULL OR lower(delivery_interval) >= %s)
              AND (%s::timestamptz IS NULL OR lower(delivery_interval) < %s)
            ORDER BY id
            """
            ).format(cols=sql.SQL(_OBS_SELECT)),
            (dataset_id, start, start, end, end),
        )
        self._conn.rollback()
        return tuple(
            StoredObservation(r["id"], r["run_attempt_id"], self._observation(r)) for r in rows
        )

    def iter_rows(
        self, dataset_id: str, *, transport: Transport | None = None
    ) -> Iterator[StoredObservation]:
        # a named (server-side) cursor: rows arrive in batches of itersize, never the whole
        # dataset at once — the restore drill reads every version (ADR-002) and must not grow
        # with the table (2026-09-24: the first scheduled drill on the demo was OOM-killed)
        query = sql.SQL(
            """
            SELECT {cols} FROM observations
            WHERE dataset_id = %s AND (%s::text IS NULL OR source_transport = %s)
            ORDER BY id
            """
        ).format(cols=sql.SQL(_OBS_SELECT))
        try:
            with self._conn.cursor(name="energy_platform_iter_rows") as cur:
                cur.itersize = 2000
                cur.execute(query, (dataset_id, transport, transport))
                for r in cur:
                    yield StoredObservation(r["id"], r["run_attempt_id"], self._observation(r))
        finally:
            self._conn.rollback()

    def _insert_events(
        self,
        cur: psycopg.Cursor[Any],
        target_id: str,
        events: Iterable[QualityEvent],
        run_attempt_id: int | None,
        now: datetime,
    ) -> int:
        n = 0
        for e in events:
            cur.execute(
                "INSERT INTO quality_events (target_id, run_attempt_id, kind, severity, message, "
                "locator, metric, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    target_id,
                    run_attempt_id,
                    e.kind,
                    e.severity,
                    e.message,
                    e.locator,
                    e.metric,
                    now,
                ),
            )
            n += 1
        return n

    def add_events(
        self,
        target_id: str,
        events: Iterable[QualityEvent],
        *,
        run_attempt_id: int | None,
        now: datetime,
    ) -> int:
        with self._conn.cursor() as cur:
            n = self._insert_events(cur, target_id, events, run_attempt_id, now)
        self._conn.commit()
        return n

    def quality_events(
        self, target_id: str | None = None, *, kind: str | None = None
    ) -> tuple[StoredEvent, ...]:
        rows = self._all(
            "SELECT * FROM quality_events WHERE (%s::text IS NULL OR target_id = %s) "
            "AND (%s::text IS NULL OR kind = %s) ORDER BY id",
            (target_id, target_id, kind, kind),
        )
        self._conn.rollback()
        return tuple(self._event(r) for r in rows)

    # ---------------------------------------------------------------- test support

    def truncate_all(self) -> None:
        """Empty every table (tests only). Sequences restart."""
        with self._conn.cursor() as cur:
            cur.execute(
                "TRUNCATE quality_events, observation_occurrences, observations, run_attempts, "
                "runs, derivations, target_freshness, invalidations RESTART IDENTITY CASCADE"
            )
        self._conn.commit()

    def table_names(self) -> tuple[str, ...]:
        rows = self._all(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_type = 'BASE TABLE' ORDER BY table_name",
            (),
        )
        self._conn.rollback()
        return tuple(cast(str, r["table_name"]) for r in rows)

    # ---------------------------------------------------------------- freshness (ADR-037)

    def count_periods(
        self, dataset_id: str, start: datetime, end: datetime, *, transport: Transport | None = None
    ) -> int:
        row = self._one(
            """
            SELECT count(DISTINCT lower(delivery_interval)) AS n FROM observations
            WHERE dataset_id = %s AND value IS NOT NULL
              AND lower(delivery_interval) >= %s
              AND lower(delivery_interval) < %s
              AND (%s::text IS NULL OR source_transport = %s)
            """,
            (dataset_id, start, end, transport, transport),
        )
        self._conn.rollback()
        return int(row["n"]) if row else 0

    def newest_delivery_start(
        self, dataset_id: str, *, transport: Transport | None = None
    ) -> datetime | None:
        row = self._one(
            """
            SELECT max(lower(delivery_interval)) AS t FROM observations
            WHERE dataset_id = %s AND value IS NOT NULL
              AND (%s::text IS NULL OR source_transport = %s)
            """,
            (dataset_id, transport, transport),
        )
        self._conn.rollback()
        value = row["t"] if row else None
        return cast(datetime | None, value)

    def upsert_freshness(self, row: Freshness) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO target_freshness (target_id, computed_at, partition_start,
                    partition_end, expected_by, status, observed_periods, expected_periods,
                    newest_delivery_start, last_capture_at, last_capture_outcome,
                    stale_fetch_streak, source_unavailable, pipeline_failed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (target_id) DO UPDATE SET
                    computed_at = EXCLUDED.computed_at,
                    partition_start = EXCLUDED.partition_start,
                    partition_end = EXCLUDED.partition_end,
                    expected_by = EXCLUDED.expected_by,
                    status = EXCLUDED.status,
                    observed_periods = EXCLUDED.observed_periods,
                    expected_periods = EXCLUDED.expected_periods,
                    newest_delivery_start = EXCLUDED.newest_delivery_start,
                    last_capture_at = EXCLUDED.last_capture_at,
                    last_capture_outcome = EXCLUDED.last_capture_outcome,
                    stale_fetch_streak = EXCLUDED.stale_fetch_streak,
                    source_unavailable = EXCLUDED.source_unavailable,
                    pipeline_failed = EXCLUDED.pipeline_failed
                """,
                (
                    row.target_id,
                    row.computed_at,
                    row.partition_start,
                    row.partition_end,
                    row.expected_by,
                    row.status,
                    row.observed_periods,
                    row.expected_periods,
                    row.newest_delivery_start,
                    row.last_capture_at,
                    row.last_capture_outcome,
                    row.stale_fetch_streak,
                    row.source_unavailable,
                    row.pipeline_failed,
                ),
            )
        self._conn.commit()

    def freshness_rows(self) -> tuple[Freshness, ...]:
        rows = self._all("SELECT * FROM target_freshness ORDER BY target_id", ())
        self._conn.rollback()
        return tuple(
            Freshness(
                target_id=r["target_id"],
                computed_at=r["computed_at"],
                partition_start=r["partition_start"],
                partition_end=r["partition_end"],
                expected_by=r["expected_by"],
                status=r["status"],
                observed_periods=r["observed_periods"],
                expected_periods=r["expected_periods"],
                newest_delivery_start=r["newest_delivery_start"],
                last_capture_at=r["last_capture_at"],
                last_capture_outcome=r["last_capture_outcome"],
                stale_fetch_streak=r["stale_fetch_streak"],
                source_unavailable=r["source_unavailable"],
                pipeline_failed=r["pipeline_failed"],
            )
            for r in rows
        )
