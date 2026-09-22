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
