# ADR-031 — Gap detector internals: expected instants from the cadence, tolerance 2× cadence

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-20 |
| Resolves | D-4 (`02-architecture-decisions.md` §4.2), implementing its recorded default |
| Supersedes | — |

## Context

`03` Phase 2 delivers the `gap_detector` module and ADR-024 §5 fixes what it emits
(`missing_capture` → backfill within `history.max_age`, else `unrecoverable`; `unprocessed_capture`
→ replay). D-4 leaves three internals open with a recorded default: where the expected instants
come from, the tolerance window, and where the detector runs. Session protocol rule 5 (`03` §0)
requires this ADR before the default is implemented.

## Decision

1. **Expected instants** are the firing times of the manifest's `cadence.cron` evaluated in
   `cadence.timezone` over the look-back window. The platform evaluates the five-field cron
   itself (minute, hour, day-of-month, month, day-of-week with `*`, lists, ranges and `*/n`);
   no target declares a calendar of its own. The look-back window defaults to `reconcile.windowHours`
   (48 h, ADR-024 §2) and is a CLI/Helm value, never a manifest field.
2. **Tolerance** is **2 × the cadence interval**, where the cadence interval is the smallest gap
   between consecutive expected instants in the window. An expected instant younger than the
   tolerance is `pending`, not a gap; this absorbs a late CronJob start (`startingDeadlineSeconds`)
   and one missed tick without paging anyone.
3. **Classification**, per expected instant older than the tolerance, in this order: a Bronze
   capture-log entry exists and the ledger run is `processed` → nothing; an entry exists and the
   run is not `processed` → `unprocessed_capture` (the entry is reconciled into the ledger if
   missing, ADR-024 §2, and the next `process` run claims it); no entry → `missing_capture`;
   `missing_capture` older than `history.max_age` → `unrecoverable` with an alert event. Bronze,
   not the ledger, is the truth for "captured" (ADR-024 §1).
4. **Where it runs**: one platform `CronJob` per target at the target's cadence (Phase 5), and
   `energyctl gaps` by hand. The detector only writes ledger rows and quality events; it never
   fetches and never processes.

## Rationale

The default is the smallest mechanism that satisfies ADR-024 §5 without a second scheduler. A
cron evaluator is a few dozen lines of standard-library code, which is cheaper than a dependency
(`croniter` is not in ADR-019) and keeps the manifest schema unchanged.

## Rejected

- A per-target expected-interval calendar in the manifest (a second way to say what `cadence`
  already says; drifts).
- Tolerance as an absolute number of minutes (wrong for both a 15-minute and an hourly target).
- Running the detector inside `process` (couples "I did not run" with "I ran and failed"; a
  process pod that never starts would also never detect that fact).

## Consequences

- Phase 2: `energy_platform/ledger/gaps.py` (cron evaluation, classification) and `energyctl gaps`;
  Phase 5: gap-detector `CronJob` template with `reconcile.windowHours` as a value.
- Devil's advocate: a `*/15` cadence with `2 ×` tolerance reports a missed 00:00 capture at
  00:30; that is the intended "one miss is free, two is a gap".

## Verification refs

none — design decision.
