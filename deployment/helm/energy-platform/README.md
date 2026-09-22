# energy-platform Helm chart

One chart, three profiles (ADR-001 amend): the **core renders tenant-clean** — no CRDs,
every pod `restricted`-PSS clean, images by digest, requests and limits everywhere — and
anything cluster-level sits behind a values flag that is off by default.

| What | Where | ADR |
|---|---|---|
| capture / process / recapture `CronJob` per target, rendered from the manifests at deploy time | `templates/cronjob-target.yaml` + `scripts/render_target_values.py` | ADR-003 rev., ADR-033, P5-D3 |
| gap detector + freshness row | `templates/cronjob-gaps.yaml` (`energyctl gaps --all --with-freshness`) | ADR-031, ADR-037 |
| hook chain `migrate` (−10, `post-install,pre-upgrade`) → `storage-probe` (−5, only `tiering.mode=lifecycle`) → `smoke` (0, `post-install,post-upgrade,test`) | `templates/hook-*.yaml` | ADR-025 |
| Postgres per `postgres.mode` = `statefulset` \| `cnpg` \| `external` | `templates/postgres-*.yaml` | D-2, ADR-030, ADR-036 §4 |
| two MinIOs for the local profile (A `--with-lock`, B plain) | `templates/minio*.yaml` (`objectstore.local.enabled`) | ADR-036 §1 |
| NetworkPolicies: default deny; DNS; Postgres; object store; TCP 443 to public ranges for capture / recapture / backfill only | `templates/networkpolicy.yaml` | ADR-026 layer 1 |
| optional `CiliumNetworkPolicy` with `toFQDNs` from the targets' hosts | `egress.fqdnPolicy=cilium` | ADR-026 layer 3 |
| `Secret` by name, or an `ExternalSecret` behind `secrets.eso.enabled` | `templates/externalsecret.yaml` | D-7 |
| freshness exporter, `PodMonitor` / `PrometheusRule` behind `metrics.operator.enabled` | `templates/metrics-*.yaml` (Phase 5 Task 5.12) | D-6, ADR-037 |
| Postgres backup shipping, Bronze replication A → B, `move` tiering, restore drill | `templates/cronjob-*.yaml` (Phase 5 Task 5.10) | ADR-002, ADR-021, ADR-036 |

## Deploying

Never `helm install` by hand: every deploy Make target generates the targets values, sets the
image digest and runs `helm upgrade --install` with rollback-on-failure and `--wait
--wait-for-jobs` (Helm 4 spells ADR-025's `--atomic` as `--rollback-on-failure`; the Makefile
picks the flag for the Helm major it finds). A failed hook — a migration, the storage probe,
the smoke — fails the release and Helm restores the previous revision.

```bash
make deploy-local                     # kind (make local-up runs it)
make deploy-tenant ENV=demo           # deployment/tenant/values-demo.yaml on top of values-tenant.yaml
helm test energy-platform -n energy-platform --logs   # re-run the smoke on demand
```

## The Secret

`secrets.existingSecret` (default `energy-platform`) must exist before the first install. Keys:

| Key | When |
|---|---|
| `POSTGRES_PASSWORD` | `postgres.mode=statefulset` (the chart builds the DSN) |
| `ENERGY_PLATFORM_DSN` | `postgres.mode=external` (`postgres.external.dsnSecretKey`) |
| `BRONZE_ACCESS_KEY_ID`, `BRONZE_SECRET_ACCESS_KEY` | always (store A) |
| `BRONZE_REPLICA_ACCESS_KEY_ID`, `BRONZE_REPLICA_SECRET_ACCESS_KEY` | `bronze.replica.enabled` (store B) |
| `BRONZE_COLD_ACCESS_KEY_ID`, `BRONZE_COLD_SECRET_ACCESS_KEY` | `bronze.tiering.mode=move` |

The local profile generates all of them (`make local-secrets`); MinIO's root credentials are
the same keys, so nothing else has to agree. With `secrets.eso.enabled` the chart renders an
`ExternalSecret` that produces the same Secret from `secrets.eso.remoteKeys`.

## Values every environment must set

`image.digest` (the deploy target does it), `residency` (`CZ` production, `DE` demo, `local`),
`bronze.endpoint` / `bronze.bucket`, `egress.clusterCIDRs` (pod + service CIDRs of the cluster,
excluded from the capture pods' internet egress) and, for off-cluster stores,
`egress.objectStore.cidrs`. The schema (`values.schema.json`) refuses a render without the
required ones and refuses `tiering.mode=lifecycle` without a non-`STANDARD` `storageClass`.

## Gates

`make helm-lint` renders tenant, local and all-flags values and runs `scripts/check_workloads.py`
(digests, requests/limits, 05 C-43/C-44) and `scripts/check_restricted_pss.py` (A-14, C-57);
`tests/harness/test_chart.py` asserts the contract on the same renders (no CRD-backed kind in the
default render, C-56; one CronJob set per target; the ADR-025 hook chain; the egress roles).
