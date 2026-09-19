# ADR-003 (revision) — Orchestration without CRDs: CronJob + Postgres run ledger

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | supersedes ADR-003 "Argo Workflows" in `02-architecture-decisions.md` §2; source `00-assumptions.md` §3 |
| Supersedes | ADR-003 (Argo Workflows / CronWorkflows) |
| Amended by | ADR-024 (2026-09-19): `fence`, `run_attempts`, reconcile step, backfill verb |

## Context

A-1: the core chart must deploy as a tenant with no CRD installation. Argo Workflows is a cluster-scoped CRD set. V-4 on the reference cluster: `can-i create customresourcedefinitions` = **no**; Argo CRDs *are* installed cluster-wide, but `can-i create cronworkflows.argoproj.io -n $NS` = **no**. So even where Argo exists, a tenant may not be allowed to use it. The tenant requirement stands regardless of what any one cluster offers, because ČEZ's cluster is the one that matters (A-1 rationale).

## Decision

- **Trigger:** Kubernetes `CronJob` (core API, V-4: `can-i create cronjobs` = yes). One template in the Helm chart, rendered once per target from `targets/*/manifest.yaml`. Targets still cannot define topology.
- **Run coordination:** a **Postgres run ledger** owned by the platform (`runs` table: `target_id`, `scheduled_for`, `lease_owner`, `lease_until`, `state`, `image_digest`, `parser_version`, `bronze_ref`). It provides idempotency (one run per `(target_id, scheduled_for)`), lease-based concurrency control across pods, missed-run detection, and the input to the gap detector.
- **Run shape unchanged:** two steps per run, `capture` (fetch → persist raw → ack) and `process` (parse → validate → normalise → upsert → quality checks). Default implementation: **two `CronJob`s**, where `process` claims unprocessed captures from the ledger (decouples processing from capture failures). Alternative kept in the chart as a values switch: one Job with two containers and an emptyDir handoff.
- **Gap detector:** a `CronJob` reading the ledger and Silver, enqueuing replays into the ledger.
- The `CronJob` template sets `concurrencyPolicy: Forbid`, `startingDeadlineSeconds` ≥ cadence, `successfulJobsHistoryLimit`/`failedJobsHistoryLimit` small, and the `restricted`-PSS security context (A-14).

## Rationale

Argo's residual value for a two-step pipeline (UI, DAG) is small; the run ledger and gap detector were required anyway because Argo has no partition/backfill semantics. The overlap was already large; removing Argo removes a CRD dependency and a second scheduler at almost no functional cost.

## Rejected

- Argo Workflows (CRD; not creatable by a tenant even where installed, V-4).
- Dagster (second control plane).
- Airflow, Kafka, Temporal (as in the original ADR-003: volume does not justify them; Temporal disproportionate).
- Keeping Argo as an optional profile (two schedulers = entropy; the ledger would still be needed).
- `CronJob` alone without a ledger (see devil's advocate below).

## Consequences

- `02` ADR-003 body replaced; ADR-004 replay and gap detector reference the ledger.
- `03` Phase 2 gains `ledger/` module and ledger migrations; Phase 5 loses the Argo `CronWorkflow` deliverable and gains "CronJob template rendered per target" and "run ledger".
- Silver rows carry `parser_version` and `image_digest` from the ledger (needed by ADR-016 repair).
- **Devil's advocate:** `CronJob` has weak missed-run semantics (`startingDeadlineSeconds`) and no cross-target concurrency control; both are supplied by the ledger, which is why the ledger is **not optional**. Loss of visibility versus the Argo UI is compensated by the ledger being a queryable table and by the freshness SLI (ADR-012).

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-4 · CONFIRMED — CRD create "no"; cronjobs "yes"; Argo CRDs present but `cronworkflows` create "no".
