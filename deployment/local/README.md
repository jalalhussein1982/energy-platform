# `local` profile — kind + Cilium on a laptop (ADR-010)

```bash
make local-up        # ≈ 6–10 min the first time (image build, Cilium and node image pulls)
make smoke-test      # helm test (the smoke hook again), freshness metric, restore-drill dry run
make local-down
```

**Prerequisites:** Docker with ≥ 4 GB of memory for its VM, `kind` ≥ 0.33, `helm` ≥ 4 (3.x also
works: the Makefile picks `--atomic` or `--rollback-on-failure` by major), `kubectl`, `uv`.
No credentials: `make local-secrets` generates the Postgres password and the MinIO keys into
the one Secret the chart consumes (`energy-platform`); nothing is read from your environment.

**Why a registry container** (`kind-registry`, `127.0.0.1:5001`): the chart only accepts an
image by digest, and an image loaded with `kind load` has no resolvable `name@digest` for
containerd. `make local-image` pushes the platform image to the kind-attached registry and the
push's digest is what the deploy sets — the same by-digest path a real registry gives.

**What runs** (namespace `energy-platform`, context `kind-energy-platform`): one Postgres
StatefulSet (WAL archiving on), MinIO A (Object Lock + versioning, four erasure-coded paths on
one volume) and MinIO B (plain), the `capture` / `process` / `recapture` CronJobs of every
committed target, the `gaps` CronJob (gap detector + freshness row), the replication, backup
and restore-drill CronJobs, the freshness exporter. Hooks on every deploy: `migrate` → `smoke`
(one fixture capture+process in a throwaway schema and Bronze). Layer-1 egress is verified by
three Jobs after the deploy (`make local-egress-test`); offline, set `LOCAL_EGRESS_OFFLINE=1`
to skip the one assertion that needs the internet — it is reported as SKIP, never as PASS.

**The capture CronJobs fetch live** from OTE and ČEPS every 15 minutes while the cluster is
up (the same bounded requests as production; ADR-033 politeness). Suspend them when you do not
want that: `kubectl -n energy-platform patch cronjob -l energy-platform.io/role=capture -p
'{"spec":{"suspend":true}}'`.

Looking around:

```bash
kubectl --context kind-energy-platform -n energy-platform get cronjobs,jobs,pods
kubectl --context kind-energy-platform -n energy-platform exec -it energy-platform-postgres-0 -- psql -U energy -d energy -c 'select target_id, state, count(*) from runs group by 1,2'
kubectl --context kind-energy-platform -n energy-platform port-forward svc/energy-platform-minio-a 9000:9000   # then any S3 client with the keys from the Secret
```

Why Cilium: kind's default CNI (kindnet) does not enforce `NetworkPolicy`, so the ADR-026
layer-1 claim would be untestable. Cilium runs in tunnel mode with `policyEnforcementMode:
default`; the chart uses only the standard `NetworkPolicy` API (no `CiliumNetworkPolicy` unless
`egress.fqdnPolicy=cilium`).
