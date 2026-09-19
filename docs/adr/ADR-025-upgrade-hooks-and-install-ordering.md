# ADR-025 — Upgrade verification hooks and first-install ordering

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | Codex review F07; amends ADR-016 §2 and §3, ADR-021 §3 |
| Supersedes | ADR-016 §2 "`helm test` hook" as the automatic rollback trigger; ADR-021 §3 "a `helm test` hook … fails the deploy" |

## Context

ADR-016 §2 promised automatic rollback from `helm upgrade --atomic --wait` plus a `helm test`
hook. A hook annotated `test` runs only when an operator invokes `helm test`, after the upgrade
has already completed; its failure cannot roll anything back. ADR-016 §3 ran migrations as a
`pre-upgrade` hook, which never runs on first install, so an empty environment would start
without a schema. ADR-021 §3 attached the storage probe to the same non-blocking hook. A CronJob
also installs "successfully" without any workload ever running, so the release needs a hook that
executes a real capture+process itself.

## Decision

1. **Hook chain, in weight order** (all Jobs: `restricted` PSS, requests/limits, image by digest,
   `helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded`, failed hook pods kept for
   inspection):

   | Job | `helm.sh/hook` | weight | Does |
   |---|---|---|---|
   | `migrate` | `post-install,pre-upgrade` | `-10` | Alembic upgrade to head; refuses if the current schema is newer than the chart's expected range |
   | `storage-probe` | `post-install,post-upgrade` | `-5` | ADR-021 probe; rendered only when `bronze.tiering.mode=lifecycle` |
   | `smoke` | `post-install,post-upgrade,test` | `0` | one fixture capture+process against the new image; asserts one ledger row `processed` and one Silver row; the `test` annotation lets an operator re-run it with `helm test` |

2. **Automatic rollback is the hook failure under `--atomic`.** Every deploy Make target runs
   `helm upgrade --install --atomic --wait --timeout <T>`. A failed hook marks the release failed
   and Helm restores the previous revision (on first install: uninstalls). Nothing else is
   required for "automatic".

3. **First-install ordering.** `post-install` hooks run after the chart's resources are created
   and, with `--wait`, ready; so in `postgres.mode=statefulset|cnpg` the database is up before
   `migrate` runs. In `external` mode the DSN must be reachable at install time; `migrate` fails
   fast otherwise. Re-running install after a partial failure is safe: Alembic is idempotent and
   hook Jobs are recreated (`before-hook-creation`).

4. **Migrations and rollback.** On upgrade, `migrate` (expand step) runs before the new image
   and is **not** undone by an automatic rollback; ADR-016 §3 already requires every migration to
   be compatible with code N−1, which is what makes that safe. Downgrade scripts exist for the
   drill and for abandoning an expand step deliberately, not for automatic rollback.

5. **Drill (ADR-016 §6, Phase 5):** deploy revision N; deploy N+1 with (a) an image whose parser
   fails the smoke fixture, then (b) `bronze.tiering.mode=lifecycle` against a gateway that reports
   `STANDARD`; assert for each: previous revision active, schema unchanged and compatible, every
   Bronze capture written by the failed attempt still present and reconciled (ADR-024).

## Rationale

Helm's own lifecycle does what ADR-016 wanted, as long as the check runs *inside* the upgrade.
Using the same Job for the gate and for `helm test` keeps one smoke definition and gives the
operator a manual re-run.

## Rejected

- A deploy script that runs `helm test` after upgrade and calls `helm rollback` on failure
  (two commands, a window in which the bad release is live, and a script to keep correct).
- `pre-install` migrations (database not yet created on first install).
- Argo Rollouts / Flagger (CRDs; ADR-016 already rejected).

## Consequences

- ADR-016 §2/§3 and ADR-021 §3 amended by this ADR; text retained as history.
- `03` Phase 5: chart deliverable names the three hook Jobs and the `--install --atomic --wait`
  Make target; drill adds the storage-probe injection.
- Devil's advocate: a `post-upgrade` smoke that fetches nothing (fixture only) cannot detect a
  broken egress path. Accepted: egress is verified by the freshness SLI over the next two cadences
  (ADR-016 §2 confirmation step, unchanged) and by the Phase 5 live egress test (ADR-026).

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-4 · CONFIRMED (hook Jobs are ordinary Jobs; restricted PSS
applies to them). Helm hook and `--atomic` semantics from the Helm 3 documentation cited in
`codex-review/06-primary-source-checks.md`.
