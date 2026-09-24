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

### 2.1 Layer 1 on the reference cluster and on the demo (Phase 9, 2026-09-23)

**Reference cluster (V-11, `00` §5): enforced.** In `hussein-ns` (RKE2, Calico) a
restricted-PSS probe pod reached OTE (200). A NetworkPolicy selecting only its label, with
egress limited to DNS, made the same request time out (curl 28, name still resolved), and with
the policy deleted it got 200 again. Nothing was left in the namespace.

**Demo: enforced only after a pod has started.** `deployment/local/egress-test-job.yaml`
applied in the demo namespace failed twice out of two, on the agent: capture → OTE 302 (right),
**capture → `169.254.169.254` reachable** and **process → OTE reachable** (wrong), while the
capture pod's second request (`10.0.0.1`), about a second after its first, was rejected (curl
7). The chart's seven policies were present and matched the pods' labels, and kube-router's
netpol chains were programmed on both nodes. The isolating test was one process-role pod that
made the same request twice, at start and 15 s later:

```text
first    up=41435.45 http=200 connect=0.002348s rc=0      ← metadata answered at container start
after15s up=41450.66 http=000 rc=7                        ← refused once the pod's rules existed
```

Probes with a sub-second timeout were refused from their first attempt in two other runs, so the
window is short (≤ ~1 s) and varies. The cause is that kube-router programs a new pod's policy
after the pod is running (Cilium on kind programs it before). The metadata service serves the
node's `user_data`, which holds the k3s join token. The fix for the platform's own pods is the
policy gate (`egress.policyGate`, ADR-026 amendment 2, `05` C-65). Blocking pod traffic to the
metadata address at node level covers every pod; that is a node change left to the author.

**The gate, live (2026-09-23, revision 6).** Every platform pod created after the deploy runs
`egress-policy-gate` first ("enforced after 0.26–0.41 s (2 attempts)"). The same three egress
Jobs with the gate in front (the platform image as the init container, curl at t=0 in the main
container) ran three times: **9 of 9 PASS** (capture → OTE 302; capture → metadata and
`10.0.0.1` refused, curl 7; process → OTE refused), against **0 of 3** passing runs without it.
In every gated pod the canary was already refused on the first two attempts, so the observed
safety is partly the delay an init container adds before the main container starts. The gate's
guarantee is that the work does not start while the canary answers, and that the pod fails
closed if it keeps answering.

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
Nothing runs on the reference cluster (ADR-028).

### 4.1 The demo, live (2026-09-23)

At the author's request the agent ran the Level 3 steps with the CLIs: OCI budget alert (the
tenancy allows one budget per compartment; the author's €1 `zero-spend-guard`, which mails on
any spend, gained a €10 forecast rule; Hetzner has no budget API), deletion of the 2026-09-22
scratch buckets, `terraform apply`, the two repository variables, the two Secrets (`ghcr-pull`
from a classic PAT with `read:packages` only, verified against `ghcr.io` first), the workflow.

The first real apply and deploy found six defects the mock tests and kind could not, each fixed
with a test (commits 3b478a8 … 12cc4f6):

| # | Symptom on the demo | Cause | Fix |
|---|---|---|---|
| 1 | `terraform apply` partial: "reading S3 Bucket … couldn't find resource" | Hetzner's gateway lists a new bucket late; the provider marked it tainted | untaint, plan the two missing resources (versioning, lock rule), apply |
| 2 | cloud-init "Failed loading yaml blob", no k3s at all | `indent()` skips the first line and the embed sat at column 0 | embed at the block's indentation; mock tests parse the rendered cloud-init |
| 3 | `/var/lib/rancher/k3s/storage` on the root disk | the provider pre-formats the volume without a label; `LABEL=` matched nothing, `nofail` hid it | fstab by the by-id path; stop before k3s if not mounted |
| 4 | Helm: `replicasets.apps is forbidden`, rolled back | `helm --wait` reads ReplicaSets; the deployer Role could not | Role gains read-only `replicasets`, `controllerrevisions` |
| 5 | k3s crash-loop: node IP `10.10.1.10` not found | the private network arrives after first-boot network setup (a race) | netplan DHCP for the private interface; wait for the address before k3s |
| 6 | Postgres on the agent's root disk; then `pg-wal-ship` "Connection refused" | local-path is node-local and only the server has the volume; kube-router rejects a new pod's first packets until its policy rule exists | `postgres.nodeSelector` (demo: the server); backup jobs `pg_isready` before connecting; archive paths per Postgres system identifier (ADR-036 amendment 1 §6) so the reinstalled cluster could not collide with the first one's locked WAL |

Replacing the server re-creates the k3s CA: the agent must be replaced with it (`-replace`), and
`DEMO_CLUSTER_CA`, the admin kubeconfig and the namespace Secrets redone.

State at 13:00 UTC: server `46.225.239.152` (API `:6443`, anonymous → 401, TLS verified against
the CA for the public address), agent joined, Postgres on the server's 10 GB volume, release
`energy-platform` revision 2 deployed by `gha:jalalhussein1982/energy-platform` over OIDC (the
identity can read ReplicaSets, cannot create them, cannot list nodes). Captures, gaps and
process succeed every 15 minutes against OTE and ČEPS; `pg-wal-ship` every 10 minutes. One manual
pass of the backup chain on the real stores: WAL ship 8 s, base 15 s (`backups/postgres/
7688704544311951385/base/20260923T124604Z`), replication Hetzner → OCI 10 s verified, **restore
drill from OCI 796 s**: restored database 337 s, Bronze-only rebuild 417 s, every target
identical or live ⊆ rebuild (82–88 replica captures per 15-minute target; the rebuild is ahead
because live has not yet processed the first release's captures).

### 4.2 Changing the authentication file or the RBAC without a new server (ADR-035 amendment 1)

The servers ignore `user_data` changes, so a template change never replaces them. To bring a
change of `authn.yaml.tftpl` or `rbac.yaml.tftpl` to the running demo:

```bash
make terraform-plan-hcloud             # must show no resource change, outputs only
terraform -chdir=deployment/own-cluster/terraform/roots/hcloud apply <that plan>   # author
make demo-reconfigure                  # SSH as root (admin key), writes both files, restarts k3s, waits for /readyz
kubectl --kubeconfig <admin> -n energy-platform auth can-i get secrets --as gha:<owner>/<repo>
```

Tenant deploys keep Helm's release records as ConfigMaps (`TENANT_HELM_DRIVER=configmap`), so by
hand it is `HELM_DRIVER=configmap helm -n energy-platform history energy-platform`. A release
that still has Secret-stored records is moved once with
`make helm-driver-migrate KUBECONFIG=<admin>` (then `DELETE_SECRETS=1`). Note that `kubectl auth
can-i create pods/exec` asks about a pod **named** `exec`; subresources need
`can-i create pods --subresource=exec`.

2026-09-23, first use (G1, Phase 9): plan = outputs only (`authn_yaml` updated, `rbac_yaml`
added), applied; revisions 1–3 copied to ConfigMaps; `demo-reconfigure` 16 s; the 17:15 UTC
captures and gaps ran normally after the restart. The identity `gha:jalalhussein1982/energy-platform`:
`get`/`list secrets` yes → **no**; `create pods --subresource=exec|portforward|attach` → **no**;
`create cronjobs`, `create configmaps`, `get replicasets` yes; `list nodes` no.
The first `deploy-demo` run after the change
([35894749370](https://github.com/jalalhussein1982/energy-platform/actions/runs/35894749370),
17:19 UTC) logged the claims `{"repository": "jalalhussein1982/energy-platform", "ref":
"refs/heads/main", "job_workflow_ref": "jalalhussein1982/energy-platform/.github/workflows/deploy-demo.yml@refs/heads/main",
"event_name": "workflow_dispatch"}`, authenticated, and **upgraded** the release to revision 4
under the ConfigMap driver (history 1–4; no re-install). The three Secret-stored records were
then deleted (`DELETE_SECRETS=1`); the namespace holds only `energy-platform` and `ghcr-pull`.
From here on `deploy-demo` also runs on a push to `main` that touches what the demo runs
(Phase 9, G6).

### 4.3 Incident, 2026-09-23: T2 backfills and corrections stored today's file (ADR-033 amendment 2)

Found while measuring publication times from the capture log (Phase 9, G8), not by an alert.

- **What the data showed:** 16 T2 payloads (today's XLSX) mapped under 21 and 22 September as
  well as 23 September. Three corrections of T2 got a 304 and were recorded with the blob of
  the 23 September run (runs `2026-09-21T08:30Z` attempt 2, `2026-09-21T21:45Z` attempt 3,
  `2026-09-22T00:30Z` attempt 2). On every target, correction attempts read as
  `content_changed` even with an identical payload hash (the E1 run of 22 September:
  the same SHA-256 on ten attempts, "changed" from the third).
- **Detected but not raised:** T1's cross-check wrote 9 544 `reconciliation_mismatch` events
  from 12:33 UTC (`price_vwap 2026-09-22T17:30Z: soap=432.00 vs copy=371.86`). No alert rule
  read them.
- **Cause:** the T2 discovery page lists the newest file and the fetch took its first link
  for any delivery day; the capture baseline was the target's newest entry (another day's
  resource). T1, T3, E1 and the imbalance settlement put the date in the request and are
  unaffected.
- **Fix:** ADR-033 amendment 2 (`05` C-66), live from revision 7 (18:15 UTC). **Repair:**
  corrective re-capture; Silver is not edited (a production database mutation is Level 3). The
  wrong versions stay in history.
- **State at 21:35 UTC:** 21 September is repaired. Its correction now requests the day's own
  file with that day's validators (a legitimate 304 with that day's blob), and its current view
  holds no row from another day's file. **22 September cannot be repaired by capture:** OTE has
  no `IM_15MIN_22_09_2026_EN.xlsx` (404; the page links `IM_STANDARD_TRADE_22_09_2026_EN.xlsx`
  that day), so T2's corrections for that day end `source_unavailable` (the recapture Job exits
  1 each hour until the day leaves the 3-day window), and **672 current-view rows of
  22 September (T2's own metrics) still carry 23 September's values.** T1, the system of record
  for `price_vwap` and `volume_total`, is correct. Removing the wrong versions is the author's
  decision (a production database change). They are exactly the T2 rows whose payload is mapped
  to more than one date (**2026-09-24:** the repair is
  `deployment/own-cluster/repairs/2026-09-22-t2-wrong-day.sql` — one transaction that aborts
  unless the set is exactly 672 rows, deletes them and prints what is left; run command in its
  header. The agent could not run or even count it: its classifier refuses production reads and
  writes. After the deletion, **do not `replay`** the 22 September runs of
  `ote_intraday_market_xlsx`: a replay re-processes each run's recorded capture, and those
  captures are the wrong blob (`energy_platform/runtime/replay.py`). Silver loses nothing that
  Bronze and the fetch log do not keep):

  ```sql
  SELECT id FROM observations
   WHERE dataset_id = 'ote.idm_continuous' AND source_transport = 'xlsx'
     AND local_date = '2026-09-22'
     AND payload_sha256 IN (SELECT payload_sha256 FROM observations
                             WHERE dataset_id = 'ote.idm_continuous' AND source_transport = 'xlsx'
                             GROUP BY 1 HAVING count(DISTINCT local_date) > 1);
  ```

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

**First run on GitHub** (Phase 9, G5): `weekly-drills` dispatched on `main` at 2026-09-23 16:56 UTC,
run [35892167897](https://github.com/jalalhussein1982/energy-platform/actions/runs/35892167897),
**green on the first attempt in 5 min 49 s** on `ubuntu-24.04`: `local-up` 2 min 30 s (kind +
Cilium + registry + atomic deploy; egress PASS 3/3 — capture → OTE 302, capture → metadata and
private addresses blocked, process → OTE blocked), `rollback-drill` 3 min (baseline deployed;
failing smoke and failing storage probe each "upgrade failed as expected", then the nine
assertions PASS: release deployed, both values restored, schema `0003_freshness`, runs and
observations unchanged, 25 CronJobs, no smoke schema left behind), `local-down`. No fix was
needed. The scheduled Monday 04:30 UTC run is the recurring evidence from now on.

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

### 8.1 Clean-clone run on a machine that has never seen the repository (Phase 8, 2026-09-23)

A throwaway Hetzner `cx33` (4 vCPU, 8 GB, Ubuntu 24.04, GNU Make 4.3), created and deleted with
`hcloud` (plan P8-D1). Tools at the Makefile's pins: Docker 29.8.1, kind v0.33.0, helm v4.3.0,
kubectl v1.37.0, uv 0.11.7. `git clone` of the public repository, then the README's reproduce block.

| Attempt | Commit | Result |
|---|---|---|
| 1 | `59a4e0c` | `make check` **failed at collection**: `ImportError: no pq wrapper available` — psycopg needs the system **libpq**, present on the author's Mac (Homebrew PostgreSQL) and on GitHub's runners, absent on a fresh Ubuntu. With `libpq5` installed: 815 passed. `make local-up` **passed** (kind + Cilium, image by digest, atomic deploy with the migrate and smoke hooks, egress 3/3). `make smoke-test` **failed with Error 143** after "gaps + freshness row written": the recipe `wait`s for the port-forward it has just killed, and GNU Make 4.x runs recipes with `.SHELLFLAGS -e` (Make 3.81 on the Mac ignores it; CI never runs `smoke-test`). |
| 2 | `cc7842a` (the `|| true` fix), a fresh clone | `make check` exit 0, **815 passed** (73 s); `make local-up && make smoke-test` **exit 0 in 199 s** — egress 3/3 PASS, smoke hook, gaps + freshness row, freshness metric present, restore-drill dry run OK. |

The README lists libpq among the prerequisites. The VM was deleted after the run.

### 8.2 Final clean clone after Phase 9 (2026-09-23)

The same recipe (P9-D12) on a new throwaway `cx33` (Ubuntu 24.04, GNU Make 4.3; Docker from
get.docker.com, kind v0.33.0, helm v4.3.0, kubectl v1.37.0, uv 0.11.7 from the release tarball
checked against its SHA-256; `libpq5`). The run executed under `nohup` on the VM, cloning
`c3b95f2` at 21:43:24 UTC:

| Step | Result |
|---|---|
| `make check` | exit 0, **875 passed** (56 s) |
| `make local-up && make smoke-test` | **exit 0 in 229 s**; egress 3/3 PASS; smoke hook, gaps + freshness row, freshness metric, restore-drill dry run OK |
| policy gate on kind | 4 platform pods ran `egress-policy-gate` and started (Cilium: enforced at once) |
| `make local-down` | exit 0 |

The VM was deleted after the run (`hcloud server list`: only the two demo nodes).

