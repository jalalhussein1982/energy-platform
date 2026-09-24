# ADR-023 — Derivation identity and current-view selection

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | Codex review F05; amends ADR-018 (version identity, `parser_version` = `contract_version`), ADR-016 §4 (repair by replay) |
| Supersedes | ADR-018 "version identity = (identity key + source_version, payload_sha256)" and "parser_version (= contract_version)" |

## Context

ADR-018 made the version identity and upsert key `(observation identity, payload_sha256)` and
stated that an identical payload rerun is a no-op. `01` §8 requires that the same raw document
parsed with a new contract version produce distinguishable rows, and ADR-016 §4 makes "replay
from Bronze with the fixed parser" the only repair for data written by a bad release. With
ADR-018's key, parser A writes a wrong sign for payload H, parser B fixes the sign, and the
corrected row has the same key: either a no-op (wrong value stays) or an overwrite (append-only
violated). ADR-018 also equated `parser_version` with `contract_version`; a bug fix changes the
implementation, not the contract.

## Decision

1. **Three versions, three meanings.**

   | Field | Meaning | Changes when |
   |---|---|---|
   | `source_version` | the source's own revision marker (`01` §6.1), or NULL | the source says so |
   | `contract_version` | semver of the registered dataset contract (`01` §6.3, registry) | the *meaning* of a field or the identity key changes (Route B, ADR-022) |
   | `derivation_id` | identity of the *implementation* that produced the row | any code or mapping that can change an output value changes |

   `derivation_id` = first 16 hex of SHA-256 over the canonical JSON of
   `{platform_version, contract_version, mapping_block, parser_ref}` where `mapping_block` is the
   manifest's `mapping` section and `parser_ref` is `generic:<parser-name>@<platform_version>` or
   `custom:<sha256 of targets/<id>/parser.py>`. A `derivations` table stores the components and
   `registered_at`. The ledger and Silver carry `derivation_id`; the name `parser_version` is
   retired.

2. **Version identity and upsert key** = `(observation identity, payload_sha256, derivation_id)`,
   with observation identity = identity key + `source_version` as in `01` §8. Consequences:
   - exact retry (same capture, same derivation) inserts nothing;
   - same payload, new derivation appends a new version row; the old row stays;
   - a provider correction (new payload) appends regardless of derivation.

3. **Current-view selection**, per observation identity, in this order:
   1. highest **ordering basis** — `source_published_at` when present, else `fetched_at` of the
      *capture that produced the row* (never the replay time);
   2. among equal ordering basis (same capture), highest `contract_version` (semver), then latest
      `derivations.registered_at`;
   3. among rows still tied (should not occur; two derivations registered in one transaction),
      the higher `derivation_id` lexicographically, and a quality event is raised.

   The view records `ordering_basis` (`source_published_at` | `fetched_at`) and exposes
   `superseded_by` computed, not stored. Nothing is deleted or updated in place.

4. **Repair semantics.** `energyctl replay --derivation <bad>` enqueues a replay for every
   capture that has a Silver row with that `derivation_id`; the corrected rows outrank the bad
   ones under rule 3.2 because they come from the same captures. Replaying an *older* capture
   never outranks a newer capture because rule 3.1 is decided by the capture, not the replay.

5. **NULL `source_version`** is a value in the observation identity (`IS NOT DISTINCT FROM`
   semantics in the unique index), so identical retries stay idempotent for sources that publish
   no version.

6. **Proofs required (Phase 2 tests, all offline):** exact retry adds nothing; same payload +
   new derivation appends and becomes current; older capture replayed with newer derivation does
   not become current over a newer capture; T1/T2 ownership rules (`01` §3) hold across both
   operations; NULL `source_version` retry is a no-op.

## Rationale

Provider revision and derivation are orthogonal axes. Keeping both in the key preserves the
append-only history the design promises and makes ADR-016 §4 repair a real operation instead of a
no-op. Deciding "current" by the capture's ordering basis first keeps `01` §8's "older arrival
after newer must not become current" true under replay.

## Rejected

- Overwriting in place on replay (violates append-only; loses the audit trail of the bad release).
- Treating a parser fix as a `contract_version` bump (conflates semantics with implementation;
  forces Route B admission churn for bug fixes).
- Making replay time the ordering basis (an old capture replayed today would become current).

## Consequences

- ADR-018: version identity and the `parser_version` sentence are superseded by this ADR; the
  rest stands.
- ADR-003 rev. / ADR-016: ledger and Silver lineage column is `derivation_id`; `--parser-version`
  becomes `--derivation`.
- `03` Phase 1 `EnergyObservation` fields: `source_version`, `contract_version`, `derivation_id`,
  `source_published_at`, `fetched_at`, `processed_at`. Phase 2: `derivations` table, unique index
  with NULL-safe `source_version`, current view, the six proofs.
- Devil's advocate: every platform release changes `derivation_id` for every target, so a
  release followed by a full replay doubles Silver row count. Accepted: replay is opt-in per
  derivation, and a release without a replay leaves existing rows current.

## Amendment 1 (2026-09-24) — the owning transport ranks first; a per-transport current view

**Context.** Review 2 (DC-03, `codex-review/2026-09-24/03-data-correctness.md`) reproduced
on PostgreSQL what decision 3 permits: `01` §3 rule 2 names T1 (SOAP) the system of record for
`price_vwap` and `volume_total`, the registry carries `owner_transport`, and the current view
ranked only by ordering instant — so the XLSX copy, fetched a minute later, became canonical,
and a `transport="soap"` filter on the canonical view returned nothing. The live demo showed
288 current XLSX rows against 96 SOAP rows for each owned metric.

**Decision.**

1. Decision 3 gains rule 0: per observation identity, among the rows whose metric has an
   `owner_transport` in the registry, the owning transport's rows rank first; the rest of the
   order (ordering basis, contract semver, derivation registration, derivation id) applies
   within. A metric without an owner is unchanged.
2. The row records its owner: `observations.owner_transport` is written by the store at commit
   from the registry (never by a mapping); migration `0004_ownership` adds the column,
   backfills it from the registry and rebuilds the view. The SQL view and the memory store
   share `store.ordering.rank`.
3. **Per-transport current.** `Store.current_rows(transport=X)` returns X's own current row per
   identity (`observations_current_by_transport`), not the canonical row filtered by transport,
   so the reconciliation copy of an owned metric stays selectable. `process` compares a
   document with each other transport's own current rows (`01` §3 rule 2), not with the
   canonical view, where the copy would never appear.

**Proof (both stores, `make db-test`):** `tests/store/test_store.py::test_review2_dc03_…`
(both arrival orders), proof 4 rewritten with differing values;
`tests/runtime/test_review2.py::test_dc03_…` through capture and process.

## Verification refs

none — design decision.
