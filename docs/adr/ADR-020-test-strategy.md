# ADR-020 — Test strategy

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-6 (`02-architecture-decisions.md` §4.1) |

## Context

ADR-008 requires golden-value tests; ADR-010 forbids network in CI; `01-data-scope.md` §7 and §9 list required fixtures. Default adopted; no verification result touches this item.

## Decision

- **Fixtures are Bronze objects**: a recorded capture (blob + capture-log entry) under `targets/<id>/fixtures/`, produced only by `energyctl record-fixture` (opt-in network). No VCR cassettes.
- **Goldens are YAML** (`targets/<id>/tests/golden/*.yaml`): expected canonical rows for a fixture, values checked by a human against the source document, including at least one negative price, one NULL, and one DST-day file where the source has one.
- **Property tests with Hypothesis** for DST (92/100 intervals), interval-convention and sign-inversion mapping, and decimal parsing.
- **Nightly live smoke** (not in PR CI): one bounded live read per committed target, asserting shape only, never values; failures open an issue, never block merges.
- A target without fixtures or goldens **fails test collection**.
- Fixtures committed to the repository are **synthetic copies of the real shape** until source redistribution is confirmed (01 §10); real captures stay in local evidence.

## Rationale

Bronze-as-fixture means the test input is literally what production stores, so a parser that passes tests passes on real captures. YAML goldens are diffable in review, which is where mapping-level data poisoning (ADR-008) is caught.

## Rejected

VCR cassettes (second capture format, HTTP-level, tempts fetch code in targets); JSON goldens (no comments for reviewer notes); live tests in PR CI (ADR-010).

## Consequences

Phase 1 property tests, Phase 3 contract-test harness and collection failure, Phase 4 nightly workflow.

## Verification refs

none — design decision.
