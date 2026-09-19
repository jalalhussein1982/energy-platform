# ADR-018 — Canonical schema details (ADR-011 parameters)

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-2 (`02-architecture-decisions.md` §4.1); feeds ADR-011 in `docs/04-contracts.md` |

## Context

ADR-011 fixes the direction (bitemporal, DST-safe, explicit conventions). B-2 asks for the three concrete choices. `01-data-scope.md` §6–§8 already specifies identity keys, version identity and ordering; this ADR must agree with it. Default adopted; no verification result touches this item.

## Decision

- Delivery interval is a **`tstzrange`** column (`delivery_interval`, start-inclusive, end-exclusive), with a generated `delivery_start_utc` for indexing; `resolution` stored alongside as an ISO 8601 duration (01 §6.2).
- Revisions are **append-only version rows** plus a **current view**: version identity = (identity key + `source_version`, `payload_sha256`) exactly as 01 §8; the current view selects by `source_published_at` when present, otherwise `fetched_at`, and records the ordering basis. Nothing is ever overwritten.
- **Both timestamps are stored**: `source_published_at` (nullable, never filled from fetch time) and `fetched_at` (always present); `processed_at` in addition. `observed_at` as a single column is **not** used; the name is ambiguous and 01 §6.1 already names the three.
- Lineage columns from the run ledger (ADR-003 rev., ADR-016): `run_id`, `parser_version` (= `contract_version` in 01 §6.1), `image_digest`.
- Upsert key (ADR-004) = version identity; a re-run with the same payload is a no-op by construction.

## Rationale

`tstzrange` gives exclusion constraints and range queries for free; append-only versions match the "never overwrite, older arrival after newer must not become current" rule in 01 §8; storing both timestamps is the only way to keep source lateness and ingestion lateness separable (01 §5).

## Rejected

start+duration columns (no native overlap constraints); a mutable "current" row with a history table (dual write); `observed_at` as fetch time (silently claims a publication time the source never gave).

## Consequences

Phase 1 `EnergyObservation` fields follow this ADR; Phase 2 migrations create the `runs` ledger and the versions table in the same migration series.

## Verification refs

none — design decision.
