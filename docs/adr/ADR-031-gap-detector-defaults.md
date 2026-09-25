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

## Amendment 1 (2026-09-25) — the run's instant is the schedule's, never the pod's start time

**Finding (review 3 R2, `codex-review/01-deep-review.md`).** `capture --live` without
`--scheduled-for` keyed the run by `datetime.now(UTC)` and the CronJob template passed no
instant, while decision 3 classifies by exact firing instants. A pod that starts at 23:15:25
therefore never served the 23:15:00 instant: every scheduled capture on the demo since
2026-09-23 became a phantom `missing_capture` after the tolerance, and the hourly backfill
(limit 8, covering the four ticks of the hour) fetched the same day's file a second time —
twice the source reads the manifests declare, a wrong ledger, no wrong value. Decision 2's
tolerance only delayed the misclassification; it could not reconcile two identities.

**Decision.**

1. A scheduled capture is keyed by the **intended instant** (`energy_platform.runtime.schedule`),
   taken in this order: the CronJob controller's own tick — a Job created by a CronJob is named
   `<cronjob>-<minutes since the epoch>` of its scheduled time, and the chart hands the pod's
   `batch.kubernetes.io/job-name` label to the capture container as `ENERGY_PLATFORM_JOB_NAME`
   by the downward API — when it decodes to a firing instant of the cadence within the last
   day; otherwise the newest firing instant of the cadence at or before now (a manual Job, a
   laptop run). `--scheduled-for` still overrides both.
2. The fallback never invents an older instant: a tick no capture served stays missing and
   decision 3 reports it. A minute-exact `now` is the last resort for a cadence rarer than the
   two-month search window.
3. Runs already keyed by a wall-clock instant on the demo stay as they are (processed, their
   captures valid); the phantom runs of their ticks were backfilled and are ordinary runs.

**Proof:** `tests/runtime/test_review3.py::test_r2_…` (the reviewer's probe inverted: a
25-second-late start, no phantom, no second fetch; the demo's own Job name decodes to its tick
and wins over a 20-minute-late start; a name without a valid tick falls back; a missed tick is
still detected; a Prague cadence and the autumn change-over day),
`tests/cli/test_cli.py::test_r2_live_capture_without_an_instant_is_keyed_by_the_schedule`,
`tests/harness/test_chart.py::test_r2_the_capture_container_learns_its_job_name_by_the_downward_api`.
The reviewer's `schedule_probe.py` no longer reproduces the defect.
