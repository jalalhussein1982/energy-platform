# ADR-038 — Durable invalidation decisions: what a rebuild must not restore

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-24 |
| Resolves | Review 2 DC-07 (`codex-review/2026-09-24/03-data-correctness.md`); amends ADR-002 (restore drill semantics), ADR-024 §2 (reconcile), ADR-033 amendment 2 ("repair is by capture, not by editing Silver") |
| Supersedes | — |

## Context

On 2026-09-23 the XLSX target stored another day's file under 21 and 22 September (ADR-033
amendment 2). 21 September was repaired by capture; for 22 September the source has no file, so
the author deleted 6 048 wrong Silver versions by hand (`docs/07` §4.3) and the runbook said
"do not replay those runs". Review 2 reproduced what that leaves open: a full rebuild from Bronze
re-processes every capture, so the deleted versions come back — and the restore drill reports
**OK** with those rows as "extra", because its rule is `live ⊆ rebuild` and a deletion recorded
only in a runbook is not an input to reconstruction. The drill proved that live *versions*
survive, not that live *decisions* do.

The platform's invariants make deletion the wrong tool anyway: Bronze is immutable evidence
(ADR-002), Silver is derived and append-only (ADR-023), and every verb that can produce rows —
`process`, `replay`, `backfill`'s processing, the drill's rebuild — reads Bronze, not a runbook.

## Decision

1. **An invalidation is a Bronze object.** `invalidations/<target>/<stamp>_<attempt>[.<derivation>].json`
   holds `target_id`, `capture_id`, optional `derivation_id` (none = every derivation), `reason`,
   `recorded_by`, `recorded_at`. It is created once (`CaptureLog.put_invalidation`, create-only
   like ADR-024 amendment 3) and never edited or deleted; replication copies the whole bucket, so
   it reaches store B with the captures it speaks about. The capture itself is never touched.
2. **The ledger mirrors it.** `reconcile` copies every invalidation of its target into the
   `invalidations` table (migration `0006_invalidations`, idempotent) before it looks at
   entries, so a fresh schema rebuilt from Bronze alone holds the decisions too.
3. **Effects, everywhere rows can come from:**
   - the current views (ADR-023) drop every *occurrence* produced by an invalidated capture (for
     the invalidated derivation, or all of them); a version with no valid occurrence left is not
     current anywhere — no row is deleted;
   - `process` of an invalidated capture (a scheduled process, a replay, a backfill's processing)
     commits no rows: state `failed`, outcome `quarantined`, an `invalidated` quality event
     naming the decision;
   - `reconcile` never names an invalidated entry as a run's generation (ADR-024 amendment 1);
   - the restore drill neither replays invalidated captures nor expects their versions from the
     rebuild; its "extra" versions are therefore real pending work again.
4. **The verb:** `energyctl invalidate -m <manifest> --capture <id>… --reason … --by …
   [--derivation <id>]` writes the object (and mirrors it when a DSN is given). It is a
   Level-3 action on production (a decision about data), run by a person.
5. **Silver deletion is retired as a repair.** The 22 September rows already deleted stay
   deleted; the author records the nine wrong captures as invalidations so the next rebuild
   agrees with live (`docs/07` §4.3 names them). Future cases are invalidated, not deleted.

## Rationale

The decision has to live where the rebuild reads. Bronze is that place, it is already
immutable and replicated, and one small JSON object per decision costs nothing. Mirroring into
Postgres keeps the views and the verbs fast and lets a restored database carry its decisions
without re-listing Bronze. Scoping by derivation covers the other repair path (ADR-023 §4): a
wrong *implementation* is fixed by replaying the capture with a new derivation, and the old
derivation's output can be voided without touching the capture's standing for the new one.

## Rejected

- **Deleting Silver rows** (what was done on 2026-09-24): invisible to every replay and to
  the rebuild; the review reproduced the consequence.
- **A runbook note** ("do not replay these runs"): not machine-readable; the drill read the
  rows as pending work.
- **A flag on the capture-log entry**: entries are immutable evidence (ADR-024 §1) and the
  decision is about the *output*, which may be wrong for one derivation and right for another.
- **Deleting the blob**: destroys the evidence the decision is about; Object Lock forbids it on
  the demo's store A in any case (ADR-036).

## Consequences

- `05` C-69; `docs/07` §4.3 and §5.3 updated; ADR-002's drill semantics read "live's valid
  versions ⊆ rebuild".
- A migration (`0006_invalidations`, with downgrade) and a new `Store` surface
  (`add_invalidation`, `invalidations`, `is_invalidated`, `attempt_captures`).
- Known weakness: a version produced by an invalidated capture *and* legitimately re-produced
  by a later capture of the same bytes keeps its later occurrence and stays current — that is
  the intended reading (the later capture is valid evidence of the same payload).

## Verification refs

`tests/store/test_store.py::test_review2_dc07_…` (both stores: hidden without deletion, scoped
by derivation, idempotent), `tests/runtime/test_review2.py::test_dc07_…` (reconcile mirrors,
replay refuses, the Bronze-only rebuild excludes and the drill passes with nothing extra),
`tests/bronze/test_bronze.py::test_invalidation_objects_…`, `tests/bronze/test_s3.py::test_invalidations_live_under_their_own_prefix_on_s3`,
`tests/cli/test_cli.py::test_invalidate_writes_a_bronze_decision_beside_the_capture_log`.
