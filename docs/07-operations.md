# 07 — Operations runbook (Phase 5)

| | |
|---|---|
| Status | Living document; every figure in it was measured on the date given, never assumed. |
| Inputs | ADR-016, ADR-021, ADR-025, ADR-026, ADR-028, ADR-035, ADR-036, ADR-037; `docs/plans/phase-5.md` |

## 1. The platform image

`deployment/image/Dockerfile` builds the one image every workload runs (capture, process,
recapture, gaps+freshness, the hook Jobs, the restore drill). Entrypoint = `energyctl`; the chart
passes the verb. Both `FROM` lines are pinned by digest and `make workload-check` refuses a tag.
The committed targets travel inside the image (a release = chart + image digest + manifests,
ADR-016 §1). Runs as uid 10001; the chart mounts `/tmp` as an `emptyDir` and keeps the root
filesystem read-only.

```bash
make image                         # docker build → energy-platform:dev
make image-digest                  # repo@sha256:… from RepoDigests (after a push)
make image-digest KIND=1           # …or from the kind node after `kind load docker-image`
```

The chart refuses to render without `image.digest` (`values.schema.json`); the deploy Make
targets pass it, so a mutable tag never reaches a cluster.

## 2. Local profile (`make local-up`)

What `make local-up` does, in order, and what proved it on 2026-09-22 (kind 0.33, Cilium 1.20.2,
Helm 4.3, Docker Desktop with 4 GB): `make image` → `kind create cluster` (one node, default CNI
off) → `make local-registry` (a `registry:2` container on `127.0.0.1:5001` attached to the kind
network; the node's containerd maps `localhost:5001` to it) → Cilium with
`policyEnforcementMode: default` → `make local-image` (push; the deploy uses the push's digest)
→ `make local-secrets` (random Postgres password and MinIO keys into the `energy-platform`
Secret) → `make deploy-local` (`helm upgrade --install --rollback-on-failure --wait=watcher
--wait-for-jobs`, hooks `minio-init` −20, `migrate` −10, `smoke` 0) → `make local-egress-test`.

Result of the first green run:

| Check | Result |
|---|---|
| `migrate` hook | Job complete (12 s): `0001_ledger`, `0002_silver`, `0003_freshness` applied in-cluster |
| `smoke` hook | Job complete: T1 `ordinary_day` fixture captured and processed in a throwaway schema and Bronze; release `deployed` |
| CronJobs rendered from the four manifests | 12 target CronJobs (capture, process, recapture × 4) + `gaps`, `pg-backup`, `replicate`, `restore-drill` |
| egress: capture pod → `https://www.ote-cr.cz` | PASS (HTTP 302) |
| egress: capture pod → `169.254.169.254`, `10.0.0.1` | PASS (both blocked, curl 28) |
| egress: process pod → `https://www.ote-cr.cz` | PASS (blocked, curl 28) |
| first `recapture-ceps-load` firing (`11 * * * *`) | completed; reported the previous delivery day as skipped (no run yet) — the ADR-033 verb never invents a run |

Two things the first attempts taught: an image loaded with `kind load` has no resolvable
`name@digest` in containerd (the pod tried Docker Hub), hence the registry container; and a
Helm hook's env list may not repeat a key under server-side apply (the smoke's `dir` Bronze is a
parameter of the container helper, not an override).
