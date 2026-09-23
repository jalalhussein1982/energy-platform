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
make image-digest FROM_LOCAL_REGISTRY=1  # …or from the kind node after `kind load docker-image`
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

## 3. Terraform (`own-cluster`)

`make terraform-validate` (2026-09-22, OpenTofu 1.12.6): `fmt -check`, `validate` and `test`
with mock providers on both roots — `hcloud` 2 runs passed (demo sizing and controls, admin-only
API), `openstack` 2 runs passed (reference sizing and controls, quota guard `agent_count <= 2`).

`make terraform-plan-hcloud` (2026-09-22 05:23, with the author's local credentials read from
`~/.config/hcloud/cli.toml`, `~/.config/energy-platform/verify.env`, `~/.oci/config`; the plan
file is under `~/.config/energy-platform/plans/`, never in the repository):

```text
Plan: 12 to add, 0 to change, 0 to destroy.
  hcloud_network, hcloud_network_subnet, hcloud_firewall, hcloud_ssh_key,
  hcloud_server.server (cx23, nbg1), hcloud_server.agent[0] (cx23), hcloud_volume.postgres (10 GB),
  random_password.k3s_token,
  aws_s3_bucket.bronze + versioning + object_lock_configuration (COMPLIANCE, 90 d)   ← store A
  oci_objectstorage_bucket.replica (versioning Disabled, retention rule 90 d)       ← store B
```

`terraform apply <planfile>` is the author's (Level 3); the cost ceilings and the checklist are
in `deployment/own-cluster/README.md`.

**Re-plan, 2026-09-23 01:11 CEST** (`hcloud-20260923-011113.tfplan`): the 2026-09-22 plan held an
admin address from another network, so it was deleted and the root re-planned with the current
one — same 12 resources, `github_repository = jalalhussein1982/energy-platform`. The author's Mac
now has Terraform 1.16.3 next to OpenTofu 1.12.6 and `make` prefers `terraform`, so this plan is
a Terraform plan: `tofu show` cannot read it ("string field contains invalid UTF-8") and it must
be applied with `terraform`. `make terraform-validate` under Terraform 1.16.3: both roots valid,
4/4 mock runs pass; the lock files are now Terraform's.

## 4. Tenant and demo deploys

`make deploy-tenant ENV=demo` layers `deployment/tenant/values-demo.yaml` on
`values-tenant.yaml`; `make deploy-demo` first checks `DEMO_OCI_NAMESPACE` (store B's endpoint
is built from it), then builds the kube context from the GitHub Actions ID token
(`scripts/oidc_kube_context.sh`, audience `energy-platform-demo`, V-14). The workflow's `image`
job builds and pushes the amd64 image with the job token and hands the digest to the `deploy`
job (plan P5-D20); the pods pull the private package with `image.pullSecrets: [ghcr-pull]`
(P5-D21); the demo values carry the providers' object-store ranges, no placeholders (P5-D22).
Still **blocked on the author** (Level 3, `deployment/tenant/README.md`): `terraform apply` of
the `hcloud` plan, the variables `DEMO_CLUSTER_URL` / `DEMO_CLUSTER_CA`, the two namespace
Secrets (`energy-platform`, `ghcr-pull`), the first workflow run. Nothing runs on the reference
cluster (ADR-028).

## 5. Backups, replication, restore (ADR-002, ADR-036)

Measured on the local profile, 2026-09-22 (MinIO A → MinIO B on one kind node; the numbers are
mechanics, not the demo's cross-provider figures, which the replication CronJob measures on
the demo cluster once it exists):

| Job | Result |
|---|---|
| `pg-backup` (2026-09-22 shape: every 5 min locally, `*/15` by default; superseded by ADR-036 amendment 1, §5.2) | `pg_basebackup -Ft -z -X stream` + `rclone copy --immutable` of base and WAL archive: 96 MiB shipped in ~4 s to `A:bronze/backups/postgres/{base/<stamp>,wal}` |
| `replicate` (`rclone copy --immutable --checksum` then `check --one-way --min-age 5m`) | first run: 1 difference — a capture had landed between copy and check, hence `--min-age`; then `0 differences found, 3 matching files` |
| `restore-drill` | see below |

The first backup attempt failed with `no pg_hba.conf entry for replication connection`: the
chart's `pg_hba.conf` gained the two `replication` lines and the Postgres pod carries a
content checksum of its config so such a change restarts it.

## 7. Observability (ADR-037 / ADR-012)

The `gaps` CronJob writes one `target_freshness` row per target every cadence; the `metrics`
Deployment (`postgres_exporter`, image by digest, default metrics off, queries in a ConfigMap)
exposes it on `:9187/metrics` with `prometheus.io/*` annotations; `PodMonitor` and
`PrometheusRule` render only behind `metrics.operator.enabled`, and the same rules ship as the
ConfigMap `<release>-alert-rules` for any scraper. Dashboard:
`deployment/helm/energy-platform/dashboards/freshness.json`.

| Metric (as exported) | Meaning |
|---|---|
| `energy_platform_freshness_age_seconds{target}` | age of the newest **non-NULL** observation the target itself delivered — the SLI |
| `energy_platform_freshness_status_active{target,status}` | 1 for the current 01 §5 state (`pending`, `partial`, `late`, `complete`) |
| `energy_platform_freshness_periods_count{target,kind}` | observed vs expected periods of the partition (92/96/100 by the DST calendar; 4 for the hourly ČEPS partition) |
| `energy_platform_source_unavailable{target}` / `energy_platform_pipeline_failed{target}` | theirs vs ours (ADR-012) |
| `energy_platform_stale_fetch_streak{target}` | consecutive unchanged captures |
| `energy_platform_freshness_computed_age_seconds{target}` | age of the row: a dead gap detector shows here |
| `energy_platform_runs_total{target,state}` | ledger runs by state |

Alerts (`_alerts.tpl`): `EnergyPlatformTargetLate` (page, 30 min), `EnergyPlatformPipelineFailed`
(page, 15 min), `EnergyPlatformSourceUnavailable` (warning, 1 h), `EnergyPlatformFreshnessStale`
(page, row older than 45 min), `EnergyPlatformExporterDown`, and — needing kube-state-metrics —
`EnergyPlatformRestoreDrillFailed`, `EnergyPlatformReplicationFailed`.

Two things the first live cycle taught, both fixed the same day: `postgres_exporter`'s driver
defaults to `sslmode=require` (the statefulset-mode DSN gets `?sslmode=disable`, in-namespace
and NetworkPolicy-scoped), and freshness must count a target's **own** non-NULL rows over every
version — the XLSX row wins the current view for the shared OTE metrics, and the XLSX carries
all 96 periods of the day with NULLs for the future, which had made T1 read 0/96 and T2 96/96
with a negative age. ČEPS load for the current hour is normally `partial` (published with a
lag); whether the previous hour turns `late` under the 2 × cadence tolerance is what the
one-week campaign (06 §6) will show, and the alert's `for: 30m` is the slack until then.

### 5.1 Restore drill on kind (2026-09-22)

| Run | What happened |
|---|---|
| 05:20, 05:30 | `fetch` failed loudly: "no base backup under B:…/base/ yet" — the first backup (05:25) was mirrored to B by the 05:30 replication, after the drill had started. Correct behaviour, not a bug. |
| 05:40 | base `20260922T033008Z` + 11 WAL segments fetched from **store B** (128 MiB, 25 MiB/s); `prep` untarred base and `pg_wal`, wrote `recovery.signal` + `restore_command`; the scratch Postgres replayed the archive ("archive recovery complete … ready to accept connections") — **PITR from B works**. The drill verb then found no capture-log entries in the replica: replication had mirrored `bronze/` (blobs) but the capture log lives under `captures/` at the bucket root (ADR-002 layout). Fixed: the whole bucket is replicated. |
| 05:50 | 16 WAL segments, 192 MiB; ledger rebuilt from B by `reconcile` (11 runs per 15-minute target, 8 for `ote_dam` from the backfill); `ceps_load` and `ote_intraday_market_xlsx` **identical** to live (236 and 1298 rows). Two comparison artefacts, fixed the same hour: `ote_dam` "ahead of live" (live had not processed its backfilled captures — its process CronJob runs 12:00–23:00) and T1's per-transport *current view* differing because the tie-break between the two OTE transports depends on processing order (ADR-023 §3). The drill now compares Silver **versions** (identity + payload + derivation → value): live ⊆ rebuild is the invariant; being ahead is reported. |

RTO figures measured on kind, 05:50 run: fetch from B 12 s, recovery to end of archive < 1 s
after start-up, `energyctl restore-drill` 7 s for four targets (≈ 1,800 Silver versions). The
demo cluster's cross-provider numbers are what its own drill CronJob will record.

### 5.2 Bounded backup footprint — ADR-036 amendment 1 (2026-09-23)

The 2026-09-22 shape shipped raw 16 MiB segments (`archive_timeout = 300`: one per five minutes
whenever anything was written, ≈ 4.5 GiB/day), never pruned the `wal-archive` volume (k3s
`local-path` does not enforce its 2 Gi request) and took 96 base backups a day, all under the
90-day lock on A and mirrored to B. Now: `archive_command` gzips each segment (`gzip -n`, via
`.part` + rename, an identical retry is success), `pg-wal-ship` (`walSchedule`, default every
10 min) `rclone move`s the archive to `A:<backupPrefix>/wal/` so the volume keeps only what is
not in A yet, `pg-backup` takes the base only (`baseSchedule`, default daily 02:15) with a
`START_WAL` marker, and the restore drill fetches only the WAL from that segment on.

Measured on kind, 2026-09-23 23:01–23:20 UTC (clean `make local-down && make local-up && make
smoke-test`: exit 0 in 257 s; local schedules: base every 10 min, WAL every 5, replication every
5, drill every 10):

| What | Result |
|---|---|
| Compressed segments in A | `…01` 2.4 MB (initdb + migrations), `…02` 575 KB (first captures), `…03`–`…05` **≈ 16 KB each** (closed by `archive_timeout`, 16 MiB raw), a `.backup` history file 201 B |
| `pg-wal-ship` | `000000010000000000000001.gz: Copied (new)` then `Deleted`; "0 segments left on the volume" after each run; the volume never held more than the segments of the last five minutes |
| `pg-backup` | base ≈ 4.3 MiB (`base.tar.gz`, `pg_wal.tar.gz`, `backup_manifest`, `START_WAL` = `000000010000000000000004`) |
| `restore-drill` 23:10 | failed loudly, "no base backup under B:…/base/ yet" — base, WAL ship and replication fired in the same minute (first-run behaviour, as on 2026-09-22) |
| `restore-drill` 23:20 | fetched base `20260922T231007Z` and **3 of 6** archived WAL files (from `…04`); `restored log file "000000010000000000000004" from archive` (the `.gz` path of `restore_command`), archive recovery complete; restored database and Bronze-only rebuild both **identical** to live (4 targets, 690 Silver versions); 31 s wall clock |

Per-cluster archive paths (amendment 1 §6, 2026-09-23): the first demo release had shipped
`backups/postgres/wal/000000010000000000000001.gz` before it had to be reinstalled; a fresh
cluster's `…01` would have collided with that locked object on every run. On kind after the
change: `pg-wal-ship` → `A:bronze/backups/postgres/7688498667088228381/wal/`, `pg-backup` → the
same cluster's `base/20260923T063545Z/`, replication copied it, and the restore drill fetched
"cluster 7688498667088228381 base 20260923T063545Z" and matched live (identical or live ⊆ rebuild
on every target).

Demo projection (not a measurement): one base a day plus about 12 closed segments an hour at
16–150 KB each — tens of MB a day into A and B instead of ≈ 4.5 GiB of WAL plus 96 bases.

## 6. Rollback drill (ADR-016 §6, ADR-025 §5)

`make rollback-drill` on kind, 2026-09-22 06:02–06:04 (`deployment/local/drills/rollback.sh`;
the platform's CronJobs are suspended for the drill and resumed by a trap):

```text
baseline: fixture=<default> tiering=none schema=0003_freshness runs=615 observations=3330 cronjobs=20
attempt failing-smoke (--set smoke.fixture=ceps_load/fixtures/ordinary_day)
  helm: post-upgrade hooks failed: Job energy-platform-smoke … Failed → rolled back (--rollback-on-failure)
  PASS release deployed · smoke.fixture restored · tiering.mode restored · schema 0003_freshness unchanged
  PASS runs 615 unchanged · observations 3330 unchanged · CronJobs 20 · no smoke_* schema left behind
attempt failing-storage-probe (--set bronze.tiering.mode=lifecycle --set bronze.tiering.storageClass=COLD)
  helm: post-upgrade hooks failed: Job energy-platform-storage-probe … Failed → rolled back
  PASS the same nine assertions
rollback-drill: PASS
```

Each failed attempt is one Helm revision marked `failed` followed by a `Rollback to N`
revision: the release never spent a second on the bad values. ADR-025 §5's "captures of the
failed attempt present and reconciled" is asserted as "production ledger and Bronze untouched"
because the smoke never writes production Bronze (P5-D5). `.github/workflows/weekly-drills.yml`
runs the same drill on a kind cluster in CI every Monday (`make ci-kind-tools` installs pinned
kind and Helm on the runner).

## 8. `make smoke-test` and the clean-clone gate

`make smoke-test` = `helm test --logs` (the smoke hook Job again: one fixture capture+process in
a throwaway schema and Bronze against the deployed image), one `gaps --all --with-freshness` run
as a one-off Job from the CronJob (on a brand-new cluster the CronJob has not fired yet, which the
first clean-clone run showed), a scrape of the exporter through a
port-forward asserting `energy_platform_freshness_age_seconds{target="ote_intraday_market"}`, and
the restore drill as a one-off Job with `RESTORE_DRILL_ARGS=--dry-run` (lists the replica, checks
the scratch server, rebuilds nothing). On kind, 2026-09-22 06:17: smoke `Succeeded` (9 s),
metric present, dry run `OK in 0.2s`.

Phase gate (03 Phase 5): from a **clean clone**, `make local-down && make local-up && make
smoke-test` — 2026-09-22 06:37–06:42, commit 93dafd9: **exit 0 in 305 s** (kind node and third-party images already cached on the laptop). Two earlier runs failed honestly and shaped the gate: a fresh cluster has no freshness row until the gaps CronJob fires, so `smoke-test` runs one gaps+freshness Job first; and store B holds no backup yet, so the drill's dry run starts an empty scratch cluster and checks reachability only (the drill pod runs as uid 999 because `initdb` needs its user in `/etc/passwd`).
