# ADR-024 — Capture durability, orphan reconciliation, backfill versus replay, lease fencing

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | Codex review F06; amends ADR-003 rev. (run ledger) and ADR-004 (replay never refetches) |
| Supersedes | — |

## Context

ADR-004 orders `FETCH → WRITE RAW → ACKNOWLEDGE → PROCESS`, ADR-003 rev. registers the run in a
Postgres ledger, and processing reads the ledger. Three gaps (F06): (1) a capture that reached
Bronze but died before its ledger row exists is invisible to every reader; (2) "replay never
refetches" leaves nothing to do when the scheduler never captured a period; (3) `lease_owner` /
`lease_until` describe a claim but not what stops an expired holder from committing after a new
holder claimed the same work.

## Decision

1. **The durable boundary is Bronze, not the ledger.** A capture is complete when its blob and
   its capture-log entry (`captures/<target_id>/<YYYY>/<MM>/<DD>/<scheduled_for>_<attempt>.json`,
   ADR-002 layout) are both written and the entry's `payload_sha256` matches the blob. The ledger
   row (`state=captured`) is written **after** that and is an index. The capture path needs no
   database: scheduling is the CronJob, idempotency is "does a capture-log entry for this
   `(target_id, scheduled_for)` already exist", attempt numbers come from listing the prefix.
   A database outage therefore never loses a source observation (ADR-004 invariant kept).

2. **Reconciliation makes orphans discoverable.** Every `process` run starts with
   `reconcile(target_id, window)`: list capture-log entries for the last `reconcile.windowHours`
   (default 48) and insert missing ledger rows with `origin=reconciled`. The restore drill runs
   `reconcile` over the full history, which is how the ledger is rebuilt from Bronze after a
   Postgres restore. Capture metadata (`fetched_at`, `source_url`, `http_status`) is copied from
   the entry, never regenerated.

3. **Runs and attempts are separate rows.** `runs` = one row per `(target_id, scheduled_for)`
   with `state` (`scheduled | captured | processed | failed | missing_capture | unrecoverable`),
   `fence` (monotonic integer) and the latest lease. `run_attempts` = one row per attempt with
   `kind` (`capture | process | backfill | replay`), `lease_owner`, `lease_until`, `fence`,
   `capture_id`, `derivation_id` (ADR-023), `outcome`, `error`. Silver rows carry
   `run_attempt_id`.

4. **Fencing at commit.** A claim is `UPDATE runs SET fence = fence + 1, lease_owner = $me,
   lease_until = now() + $ttl WHERE id = $run AND (lease_until IS NULL OR lease_until < now())
   RETURNING fence`. Every Silver write and every state transition for that run executes in one
   transaction whose statements include `... AND runs.fence = $my_fence`; a stale holder's
   transaction affects zero rows, is rolled back, and the worker exits with outcome
   `lost_lease`. Leases are renewed with the same predicate. No write outside the transaction
   can make a stale holder's partial output visible.

5. **Three verbs, never confused.**

   | Verb | Fetches? | Input | When |
   |---|---|---|---|
   | `capture` | yes | schedule | every cadence (CronJob) |
   | `backfill` | yes | a period with **no** capture-log entry | gap detector finds `missing_capture` **and** the manifest's `history.max_age` says the source still serves that period; otherwise the run is marked `unrecoverable` and alerted (a missing historical payload is reported, never silently skipped) |
   | `replay` | **no** | existing Bronze captures | gap detector finds `unprocessed_capture`, or an operator runs `energyctl replay` (by range or by `--derivation`, ADR-023) |

   ADR-004's "replay never refetches" stands; backfill is the fetching verb.

6. **Crash matrix (Phase 2 tests, offline, in-memory backends):** worker dies after blob PUT and
   before capture-log PUT (no entry → next run re-captures; the orphan blob is content-addressed
   and harmless); dies after capture-log PUT and before the ledger row (reconcile inserts it);
   Postgres down during capture (capture completes; reconcile later); two workers claim one run
   (second claim fails); lease expires and the old holder commits late (zero rows, `lost_lease`);
   period never captured and inside `history.max_age` (backfill enqueued); outside it
   (`unrecoverable`, alert); replay of a capture already processed by the same derivation (no-op).

## Rationale

Bronze is the irreplaceable tier (ADR-002); making it the durable boundary means the ledger can
always be rebuilt and never has to be trusted more than the object store. Fencing at commit is
the standard answer to expired leases; describing the lease fields without it left the invariant
"duplicate execution ≠ duplicate canonical records" resting on the upsert key alone, which does
not protect state transitions.

## Rejected

- Writing the ledger row first and Bronze second (a ledger row without a payload is a lie;
  Bronze without a ledger row is recoverable).
- A transactional outbox in Postgres (puts the database on the capture path, which ADR-004
  forbids).
- Advisory locks instead of fencing (do not survive the holder's process losing the connection
  while its worker keeps running).
- Auto-backfilling everything the gap detector finds (would silently refetch periods the source
  no longer serves and hide real data loss).

## Consequences

- ADR-003 rev.: `runs` gains `fence`, `origin`; `run_attempts` table added; the `process`
  CronJob begins with `reconcile`; gap detector emits `missing_capture` and
  `unprocessed_capture` separately.
- ADR-002: capture-log key includes `scheduled_for` and attempt; entry gains `capture_id`.
- Manifest (Phase 1): `history.max_age` (ISO 8601 duration or `none`) declares how far back the
  source serves data; the gap detector consults it before backfilling.
- `03` Phase 2 gains the crash matrix; Phase 5 restore drill rebuilds the ledger by reconcile.
- Devil's advocate: `reconcile` lists object storage on every process run. Bounded by the window
  (48 h ≈ 192 entries at 15-minute cadence) and cheap on S3 prefixes.

## Amendment 1 (2026-09-24) — capture generations: the ledger follows every Bronze generation

**Context.** Review 2 (DC-01, DC-02; `codex-review/2026-09-24/03-data-correctness.md`)
reproduced on PostgreSQL two ways a durable correction was lost. (1) A correction captured
while the ledger was down: §2's reconciliation inserts *missing* runs and advances a run only
while it has no capture id, so an existing run kept its older capture and no pending work
appeared — `reconciled=0`, the old price stayed current. (2) A correction registered while a
worker held a claim on the older capture: `mark_recaptured` changed the run's capture id but
not its fence, so the old worker's commit passed §4's fence check and wrote the old payload
over a run that now named the new one.

**Decision.**

1. **A new generation invalidates in-flight work.** `mark_recaptured` bumps `runs.fence` and
   clears the lease. A commit predicated on the previous fence affects zero rows and is
   recorded `lost_lease` (§4, unchanged); the run stays `captured` on the new capture and the
   next claim processes it.
2. **Reconcile advances generations.** For every scheduled instant in its window, `reconcile`
   compares the run's capture with the newest Bronze entry: a later attempt whose payload
   differs is a generation the ledger missed, and the run is `mark_recaptured` to it. A later
   attempt with the run's own payload is a poll, not a generation (nothing to process).
   Intermediate generations the ledger never saw (A processed, B missed, C captured) are not
   replayed live — the run advances to the newest; the restore drill's rebuild replays every
   payload change (ADR-023 amendment 2) and holds them all.
3. **The window covers corrections.** Reconcile looks back `reconcile.windowHours` **plus the
   manifest's `cadence.correction.days`**, so a correction of D-3 captured during an outage is
   found by the default 48-hour reconcile.

**Proof:** `tests/store/test_store.py::test_review2_dc02_…` (both stores: the old claim's
commit is `lost_lease`, no rows, the new claim completes);
`tests/runtime/test_review2.py::test_dc01_…` (outage, subsequent unchanged poll, D-3) and
`::test_dc02_…` through capture, claim and process.

## Amendment 2 (2026-09-24) — an abandoned replay attempt is reclaimed

**Context.** Review 2 (DC-05): a queued replay is pending only while its attempt has no
lease owner; a worker that claimed it and died left an unfinished, leased attempt on a
`processed` run, which neither `pending_runs` nor `claim` looked at again — the repair
stopped permanently after one worker failure.

**Decision.** `pending_runs(target, now=…)` also returns runs with an unfinished replay
attempt whose lease expired before `now`. `claim` closes every such attempt as `lost_lease`
(its outcome is recorded) and opens a fresh replay attempt for the new owner, under the run's
new fence. The lease model (§4) is unchanged: the dead holder, if it ever commits, loses.

**Proof:** `tests/store/test_store.py::test_review2_dc05_…` (both stores);
`tests/runtime/test_review2.py::test_dc05_…` through `replay_range`, `claim` and `process`.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-6 · CONFIRMED (object store listing and object lock, on which
the reconcile path relies).
