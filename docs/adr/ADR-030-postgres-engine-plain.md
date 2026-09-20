# ADR-030 — Postgres engine: plain PostgreSQL, no TimescaleDB

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-20 |
| Resolves | D-2 engine question (`02-architecture-decisions.md` §4.2: "engine (plain vs TimescaleDB) still open … decided by ADR before the Phase 2 schema") |
| Supersedes | — |

## Context

D-2 already fixes Postgres as a **DSN contract** with `postgres.mode = statefulset | cnpg |
external` (A-11, V-10). What is still open is whether the schema may rely on the TimescaleDB
extension (hypertables, compression, continuous aggregates) or must be plain SQL. The Phase 2
schema (ADR-018: `tstzrange` interval, append-only version rows, a current view; ADR-023:
NULL-safe unique version identity; ADR-024: `runs`/`run_attempts` with fencing) is created in
this phase and cannot be changed later without an expand/contract migration (ADR-016 §3).

## Decision

The schema targets **plain PostgreSQL 16 or newer** and uses no extension beyond what a stock
`postgres` image ships. Concretely it relies on: `tstzrange` with a generated
`delivery_start_utc` column (ADR-018), `jsonb` for the identity dimensions, a `UNIQUE … NULLS NOT
DISTINCT` index for the version identity (ADR-023 §5; PostgreSQL ≥ 15), `DISTINCT ON` for the
current view, and `SELECT … FOR UPDATE` plus a fence predicate for lease fencing (ADR-024 §4).
Every profile's `postgres.mode` must therefore provide PostgreSQL ≥ 16; the application checks
`server_version_num` at start-up and refuses an older server. Time-series optimisation, if it
is ever needed, is a Gold-tier concern (ADR-002: disposable, rebuilt), never a Silver schema
dependency.

## Rationale

- Volume does not justify an extension: three committed targets at 96–100 quarter-hours per day
  and one row per metric is on the order of 10⁶ rows per year, which plain B-tree indexes serve.
- `external` mode (managed Postgres at ČEZ, A-11) cannot be assumed to offer TimescaleDB;
  `cnpg` needs a custom image for it; `statefulset` would need a different image than the stock
  one. A schema that needs the extension would make the DSN contract false on two of three modes.
- Portability is the sovereignty argument of `02` §1.3: anything ČEZ could not reproduce or
  move is disqualifying.

## Rejected

- **TimescaleDB** hypertables for `observations`: the extension is not available uniformly
  across `statefulset | cnpg | external`; compression and continuous aggregates solve a problem
  this volume does not have.
- **PostgreSQL 14 compatibility** (no `NULLS NOT DISTINCT`): would force a `COALESCE(source_version,
  '')` sentinel into the unique index, which turns a NULL into a value inside the identity —
  exactly what ADR-023 §5 says to avoid.
- **SQLite for local/demo**: a second dialect for `tstzrange`, `jsonb` and `DISTINCT ON`; the
  demo would prove a different schema than production runs.

## Consequences

- `03` Phase 2 `silver/` and `ledger/` migrations are plain SQL (Alembic operations with explicit
  DDL, one downgrade per migration, ADR-016 §3).
- Phase 5 chart: `postgres.mode=statefulset` pins a `postgres:16` image by digest; `cnpg`
  uses the operator's default PostgreSQL 16 image; `external` documents "PostgreSQL ≥ 16" as a
  precondition and the start-up check enforces it.
- `make demo` and `make db-test` run against an ephemeral local PostgreSQL started with
  `initdb`/`pg_ctl` (offline, Unix socket) or against `ENERGY_PLATFORM_DSN` when set.
- Devil's advocate: a future high-frequency series (`kind=point`, 1-minute frequency) would grow
  faster. Accepted: it is a candidate, not a commitment (`01` §4), and native partitioning by
  `delivery_start_utc` is available in plain PostgreSQL if it is admitted.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-10 · CONFIRMED (no managed Postgres on the reference
environment; CNPG operator pre-installed; `statefulset` default for `tenant`).
