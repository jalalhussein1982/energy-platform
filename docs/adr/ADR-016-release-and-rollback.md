# ADR-016 — Release and rollback model

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | new; source `00-assumptions.md` §3 |
| Supersedes | — |

## Context

"Does Kubernetes let us roll back a bad release?" — yes for stateless code and configuration, **no** for schema, data and semantic errors. The platform must supply the invariants that make Kubernetes rollback *safe*. Workloads are `CronJob`-driven (ADR-003 rev.), so a crash does not surface until the next run.

## Decision

1. **A release is an immutable bundle**: chart version + image **digest** (never a mutable tag) + the set of target manifests. Rollback = `helm rollback <release> <revision>`. Images are retained for ≥ N revisions; CI refuses `latest` and any tag without a digest.
2. **Automatic rollback on failed upgrade**: `helm upgrade --atomic --wait --timeout` plus a **`helm test` hook** that runs one fixture capture+process end-to-end against the new image. Kubernetes does not auto-rollback a crash-looping Deployment; probes only stop the rollout. For `CronJob` workloads the post-upgrade test hook is the detection mechanism, and the **freshness SLI over the next two cadences** is the confirmation.
3. **Schema migrations are the rollback trap.** Rollback reverts the image, not the database. Therefore: migrations are **expand/contract**; every migration is compatible with version N−1 of the code; migrations run as a Helm `pre-upgrade` hook Job; a **downgrade script is required per migration and exercised in CI**; the application **refuses to start** against an incompatible schema version.
4. **Data written by a bad release is not undone by rollback.** Rollback stops the bleeding; the repair is `energyctl replay --from --to --parser-version <bad>` from Bronze, which is why Silver carries `parser_version` and `image_digest` lineage from the run ledger. Bronze immutability (object lock, V-6) is what makes this repair trustworthy.
5. **Semantic failures are invisible to Kubernetes** (wrong sign, wrong unit, no crash). Defences are upstream: golden tests in CI, quality checks in `process`, and optionally a **canary target group** (D-13: one low-risk target runs `image.canary` one cadence before the rest). Canary is optional in v1; goldens and quality checks are not.
6. **Rollback is drilled**, like restore: a scheduled job deploys revision N, then N+1 with an injected failure, and asserts automatic rollback with zero Bronze loss and correct ledger state.

## Rationale

Each numbered point closes one gap between what Helm/Kubernetes can revert and what a data platform must revert. Together they make "roll back" a one-command, safe operation for an operator with best-effort support (A-6).

## Rejected

- Argo Rollouts / Flagger (CRDs; disproportionate; not tenant-installable).
- `kubectl rollout undo` alone (does not cover chart, config, or `CronJob` resources coherently).
- Backward-incompatible migrations with a "we'll restore from backup" plan (restore ≠ rollback; loses data written since).

## Consequences

- `02` §2: this ADR appended. `03` Phase 2 definition of done: "downgrade script per migration". Phase 3 constraint matrix: "mutable image tag", "migration without downgrade". Phase 5: `helm test` hook, rollback drill.
- Devil's advocate: expand/contract doubles the number of migrations for a rename. Accepted cost; renames are rare in a bitemporal append-only schema (B-2).

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-4 · CONFIRMED (CronJob rights; restricted PSS applies to hook Jobs too); 2026-09-19 · V-6 · PARTIAL (object lock enforced on store A, which underwrites point 4).
