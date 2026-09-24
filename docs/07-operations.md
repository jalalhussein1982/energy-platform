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
→ `make local-secrets` (random Postgres password and object-store keys into the `energy-platform`
Secret) → `make deploy-local` (`helm upgrade --install --rollback-on-failure --wait=watcher
--wait-for-jobs`, hooks `bucket-init` −20 (`minio-init` until 2026-09-24, §8.4), `migrate` −10,
`smoke` 0) → `make local-egress-test`. Since 2026-09-24 the two object stores are RustFS, not
MinIO (ADR-036 amendment 4; §8.3 for why, §8.4 for the proof).

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

**2026-09-24 (ADR-026 amendment 3, review 2 DEP-05).** With the node-level metadata block in
place the metadata canary is refused from the first attempt whatever the pod's policy, so the
gate now also probes a **policy canary**: the cluster DNS service (resolv.conf's nameserver,
`10.43.0.10` on the demo) on its metrics port 9153 — pod-to-pod, so kube-router polices it; the
DNS rule allows 53 only; CoreDNS accepts connections on 9153 without the policy. An accepted
connect means the pod's egress rules are not in force yet; a refused *or* dropped one means they
are (kube-router rejects — the curl exit 7 above — Cilium drops); port 53 on the same address
must answer, or the gate stays closed. Two earlier readings were tried on the migrate hook the
same day and **withdrawn** by their own failures: the node's IP on a closed port (revision 18
rolled back to 17, 16:55 UTC — refused with or without a policy) and "dropped = policy"
(revision 20 rolled back to 19, 17:06 UTC — kube-router's denial is a refusal). The platform
kept running throughout: an atomic upgrade that fails its hook changes nothing. The three egress Jobs are to be rerun with
the node block on to confirm the first-packet behaviour under the new gate (author's action; the
previous 9 of 9 predate the node block).

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
  unless the set is exactly **6 048 rows**, deletes them and prints what is left; run command in
  its header. **The 672 above is the current view.** Profiled on 2026-09-24 (read-only): the base
  table held **nine** wrong versions of 22 September — 23 September's file at nine points of
  that day, fetched 13:37–18:10 UTC on 23 September, all before revision 7 — and every xlsx row
  under 22 September was one of them (no payload unique to the day). The current view showed the
  newest (`383dedd8…`); deleting only that one would have promoted the next. The script's first
  run (guard at 672) aborted on 6 048 as designed, nothing deleted; the guard was then set to
  6 048 with two more conditions (every payload also mapped under another day; every row fetched
  before 18:15 UTC). **Executed 2026-09-24 ~01:44 UTC** (the author approved the agent's run by
  hand): `DELETE 6048`, 0 xlsx rows left under 22 September, `COMMIT`. Afterwards the current view
  of 22 September holds T1's 192 rows (`price_vwap`, `volume_total`) and nothing from T2;
  23 September's 672 xlsx rows are untouched; the next captures (01:45 UTC) ran normally. The
  wrong blobs stay in Bronze and the attempts in the fetch log. After the deletion, **do not `replay`** the 22 September runs of
  `ote_intraday_market_xlsx`: a replay re-processes each run's recorded capture, and those
  captures are the wrong blob (`energy_platform/runtime/replay.py`). Silver loses nothing that
  Bronze and the fetch log do not keep). **Superseded 2026-09-24 by ADR-038:** deleting Silver is
  retired as a repair; the decision is recorded as an invalidation that the current view, replay and
  the restore drill honour. **Author action (Level 3):** record the nine wrong captures of
  22 September, one `energyctl invalidate -m targets/ote_intraday_market_xlsx/manifest.yaml
  --capture <id> --reason "23 September's file stored under 22 September (ADR-033 amendment 2)"
  --by <you>` each (the ids are the nine xlsx attempts of that day fetched 13:37–18:10 UTC on
  23 September, listed by `energyctl gaps`'s ledger or the SQL below), so the next Bronze-only rebuild
  no longer reports them as extra:

  ```sql
  SELECT id FROM observations
   WHERE dataset_id = 'ote.idm_continuous' AND source_transport = 'xlsx'
     AND local_date = '2026-09-22'
     AND payload_sha256 IN (SELECT payload_sha256 FROM observations
                             WHERE dataset_id = 'ote.idm_continuous' AND source_transport = 'xlsx'
                             GROUP BY 1 HAVING count(DISTINCT local_date) > 1);
  ```

## 5. Backups, replication, restore (ADR-002, ADR-036)

**RPO per failure domain (ADR-036 amendment 2, 2026-09-24):** a worker 0; the database node 15 min
(WAL shipped to A); store A or its provider = the replication interval + copy time (demo: 15 min,
`7,22,37,52 * * * *`); the whole environment = as store A plus the rebuild. Three alert rules watch
the *age* of the last successful replication, WAL shipment and base backup (kube-state-metrics),
because a job that never runs has no failed-Job metric.

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

### 5.3 The drill's memory does not grow with the table (2026-09-24)

The first **scheduled** drill on the demo (01:30 UTC; the manual drill of 23 September had
passed) ended `OOMKilled` at the Job limit of 512 MiB, after the restored database had shut down
cleanly — in the comparison step. Cause: `restore-drill` compared Silver by loading every stored
version of a dataset as Python objects (`Store.all_rows`, a tuple of `StoredObservation`), for
live and for the rebuild, and once more for the live digest; the two targets that share
`ote.idm_continuous` each loaded the whole dataset and filtered their transport in Python. At
74 886 rows (57 MB on disk) that was already past the limit, and it grew with every capture.

Fix (no chart change; the 512 MiB limit stays): `Store.iter_rows(dataset_id, transport=…)`
streams versions in `id` order — a named server-side cursor on PostgreSQL (`itersize` 2 000),
a generator on the memory store — and the drill keeps **one 16-byte fingerprint per version**
(blake2b over identity, payload hash, derivation, value) in a set per side. Missing = live −
rebuild, extra = rebuild − live, checksum = SHA-256 over the sorted fingerprints; the report
fields, messages and every existing drill test are unchanged. Memory is now a few dozen bytes
per version instead of a kilobyte per row three times over. Tests:
`tests/store/test_store.py::test_iter_rows_streams_every_version_in_id_order_and_filters_by_transport`
(memory and PostgreSQL) and `tests/runtime/test_drill.py::test_the_drill_streams_rows_and_never_materialises_a_dataset`
(a store spy fails the drill if `all_rows` is touched).

**Proof and a new finding (manual drill `restore-drill-manual-2`, 02:05–02:12 UTC, revision 12).**
The comparison **completed**: 406 s wall clock, all seven targets compared, `65 856` rebuilt
versions against `57 120` live for the xlsx target alone, inside the same 512 MiB — the OOM is
gone. The drill then **failed on its own criterion**, which the OOM (and the early manual run of
23 September) had hidden:

| Target | Rebuild vs live | Verdict |
|---|---|---|
| `ote_dam`, `…settlement_final`, `…settlement_monthly` | identical | ok |
| `ote_imbalance_settlement` | processed runs 63 < live 64 | fail |
| `ceps_load` | 84 versions live holds are missing from the rebuild | fail |
| `ote_intraday_market` | 64 missing | fail |
| `ote_intraday_market_xlsx` | 1 344 missing, 10 080 extra | fail |

Two causes, both in the drill's rule, not in the backups: **(a) superseded captures.** A
correction that finds changed content is a new capture of the same run; live keeps the version
each capture produced, but the run's `capture_id` moves to the newest, and the rebuild
(`reconcile` + `process`) replays one capture per run — so every version an earlier capture of
a run produced is "missing" although its blob is in the replica. The counts are multiples of a
day's rows (84 = ČEPS QH rows of a partial day, 1 344 = 2 × 672). **(b) replica lag.** A run
processed in live after the last replication has no capture in store B yet, so the rebuild
holds one processed run fewer. The rule tolerates the rebuild being ahead, not behind. The
10 080 "extra" xlsx versions include the nine wrong versions of 22 September deleted in §4.3:
their blobs are in the replica, so a rebuild recreates them — the documented cost of that
deletion, informational here.

**Fixed the same night (rule change in `energy_platform/runtime/drill.py`).** (a) The rebuild
now replays **every distinct payload** of a run from the replica log, oldest first and the
newest last, so the rebuild holds the version each capture produced and the run ends on its
newest capture as live does; `content_changed` is not used for this (it is a flag against the
target's newest entry, §4.3), payload hashes are. (b) The comparison is bounded by the
**replica's newest capture instant** for the target: a live version or processed run whose
capture is in the replica, or was fetched before that instant, is compared (its absence is
loss); one whose capture is newer and not replicated yet is lag, counted in a new report field
`lagging_runs` and named in the message ("N live run(s) newer than the replica's last capture
not compared"), never a failure. With no replica entry for a target at all, everything live
holds is compared and is missing — the replica never received it. Tests:
`test_a_replica_missing_a_capture_fails_the_drill` now removes a *middle* capture (loss),
`test_a_replica_lagging_behind_live_is_not_a_failure` removes the newest (lag),
`test_superseded_captures_are_replayed_so_every_live_version_is_rebuilt` forces a second
capture of a run. The test harness now stamps `fetched_at` from its clock, so capture instants
and ledger instants share one time line. The nine deleted versions of §4.3 still come back as
"extra", by design.

**Proved on the demo (manual drill `restore-drill-manual-3`, revision 13, 02:52–03:26 UTC,
Job succeeded, exit 0).** Phase 1, against the restored database: **OK in 777 s**, all seven
targets — `ceps_load` identical 8 910 versions (10 lagging runs named), `ote_intraday_market`
identical 7 896 (10 lagging), `ote_imbalance_settlement` identical 576 (1 lagging), `ote_dam`
and the two monthly targets identical, `ote_intraday_market_xlsx` live ⊆ rebuild with all
**57 120** live versions reproduced and the rebuild ahead by 11 424 (the nine deleted versions
of §4.3 among them; 3 lagging). Phase 2, the Bronze-only rebuild into a fresh schema: **OK in
1 216 s**. Peak memory seen during phase 2: 77 MiB for the drill container, 156 MiB for the
scratch PostgreSQL; the platform's captures and processing ran normally throughout. Recovery
figures for the demo at this size (≈ 75 000 Silver versions, seven targets), stated separately:
the restored-database phase 777 s (≈ 13 min); the Bronze-only rebuild into a fresh schema
1 216 s (≈ 20 min); the whole two-phase Job 02:52–03:26 UTC (≈ 34 min). Each is a replay
duration on warm infrastructure; none is a measured infrastructure-loss RTO (replacement
nodes, identities and secrets, resumed schedules are not included — review 2 DEP-01/04-topology).

### 7.1 Dashboards — Grafana, private (ADR-039, Phase 11, 2026-09-24)

`grafana.enabled` renders one Deployment (`docker.io/grafana/grafana` by digest, uid 472,
read-only root filesystem), a ClusterIP Service on 3000 and two NetworkPolicies: egress to
Postgres and DNS, ingress from the namespace. There is **no Ingress and no public address**, on
purpose: OTE's and ČEPS's data is for internal use only (`06` §1.4, §4.5). The datasource is
the read-only login role `grafana` (a member of `energy_reader`, migration 0007) that the
migrate hook creates from the Secret key `GRAFANA_DB_PASSWORD`; the admin password is
`GRAFANA_ADMIN_PASSWORD`. Both keys are part of `DEMO_SECRET_KEYS` and of `make local-secrets`.

Access, from a machine with the namespace kubeconfig:

```bash
kubectl -n energy-platform port-forward svc/energy-platform-grafana 3000:3000
kubectl -n energy-platform get secret energy-platform -o jsonpath='{.data.GRAFANA_ADMIN_PASSWORD}' | base64 -d; echo
# then http://localhost:3000 — user admin, that password
```

Two provisioned dashboards (`deployment/helm/energy-platform/dashboards/`, read-only in the
UI; the data directory is an `emptyDir`, so nothing edited there survives a restart):

| Dashboard | Panels |
|---|---|
| `energy-platform — prices and load` | intraday `price_vwap` per period with the SOAP record and the XLSX copy overlaid (a divergence is a `reconciliation_mismatch`), traded volume, day-ahead price (published for the next day), ČEPS load, imbalance settlement prices and system imbalance by version, the newest current row per dataset and transport |
| `energy-platform — freshness and ledger health` | the `01` §5 state per target from `target_freshness` (ADR-037 amendment 1), ledger runs by state, capture attempts and quality events per hour, versions · occurrences · invalidations, the newest attempt per target |

The queries read `observations_current` and `observations_current_by_transport`, so the screen
shows what ADR-023 and ADR-038 say is current, nothing else. Enabling Grafana on a running
deploy is a **Secret change first**: a missing key fails the atomic upgrade, which then changes
nothing (`kubectl -n energy-platform patch secret energy-platform --type merge -p
'{"stringData":{"GRAFANA_ADMIN_PASSWORD":"…","GRAFANA_DB_PASSWORD":"…"}}'`, Level 3).

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



### 8.3 The local profile can no longer pull its object stores (2026-09-24)

Running `make local-down && make local-up` on this laptop after Phase 11 (Docker running again)
failed twice: first on the 43-hour-old kind cluster from Phase 9, whose API server timed out
under memory pressure during the upgrade and whose DNS was broken afterwards (the smoke pod could
not resolve `energy-platform-postgres`), then on a **fresh** cluster, cleanly, at the image pull:

```text
Failed to pull image "quay.io/minio/minio@sha256:14cea493…": … unexpected status from HEAD request … 401 UNAUTHORIZED
```

From the host, `docker manifest inspect` says `no such manifest` for both pinned digests
(`quay.io/minio/minio` RELEASE.2025-09-07, `quay.io/minio/mc`), `quay.io/minio/minio:latest` and
`docker.io/minio/minio` answer 401 with an empty tag list, quay's public API for a control
repository (`prometheus/node-exporter`) answers normally, and `github.com/minio/minio` is
**archived** (last push 2026-04-24; the README now points to the commercial AIStor). Every other
pinned image — Postgres, the exporter, rclone, Grafana — still resolves. The digest pins did their
job (nothing else was pulled in their place); what they cannot do is keep a publisher from
withdrawing an image. The kind node from 2026-09-23 had the images cached, which is why the last
clean-clone run (§8.2) passed and why the problem surfaced only now.

Consequences: `make local-up` fails on any machine without the cached images, so the README's
reproduce block is annotated; the demo is unaffected (Hetzner Object Storage and OCI, ADR-036);
Grafana's local-profile check (Phase 11) stays unrun — its chart tests, `helm-lint` and the demo
deploy were the checks. Next platform change (an ADR-036 amendment, planned as Phase 12): replace
the two MinIO StatefulSets and the `mc` init job with an S3-compatible server whose images are
published and which implements Object Lock — candidates `ghcr.io/versity/versitygw` (v1.8.0,
43 tags), `docker.io/rustfs/rustfs` (1.0.0), SeaweedFS — with the same `--with-lock` bucket
semantics the local profile relies on (ADR-036 §1). The kind cluster was torn down afterwards.

### 8.4 The local profile's object stores are RustFS (Phase 12, 2026-09-24)

**The probe** (ADR-036 amendment 4, P12-D1). RustFS 1.0.0 in Docker on this laptop, exercised
with the AWS CLI 2, rclone 1.75.1 and the platform's own client — every step the local profile
relies on, in the order the platform uses them:

```text
== rustfs on http://127.0.0.1:19000 (container running)
PASS  create-bucket --object-lock-enabled-for-bucket
PASS  create-bucket (plain, B)
INFO  create-bucket again: 200
PASS  put-bucket-versioning
PASS  get-bucket-versioning Enabled
PASS  get-object-lock-configuration Enabled
PASS  put-object with COMPLIANCE retention
PASS  head-object reports COMPLIANCE (COMPLIANCE 2026-09-25)
PASS  delete of the locked version refused ((AccessDenied))
PASS  locked version still readable
PASS  second PUT keeps both versions (2)
PASS  list-objects-v2 paging (2 True True)
PASS  put-object --storage-class STANDARD
INFO  head StorageClass: <absent>
PASS  client put with lock headers (etag "4ecfe9bccb3)
PASS  client head size=10
PASS  client list paging 3 keys
PASS  If-None-Match: first True, second False
INFO  read-back: b'one'
PASS  rclone copy --immutable to B
PASS  rclone check --one-way: 0 differences
PASS  rclone --immutable refuses a changed object
PASS  rclone copy A→B (server to server, incl. locked objects)
```

Two facts from the transcript matter for the chart: a repeated create-bucket answers 200 (so
`bucket-init` checks `HEAD` first and treats 409 as "exists" for other servers), and HEAD omits
`StorageClass` for STANDARD objects, as S3 itself does. The image runs as uid 10001, initialises
`/data` and `/logs` at start (both are volumes under the read-only root filesystem), and has no
console when `RUSTFS_CONSOLE_ENABLE=false`.

**The gate** — `make local-down && make local-up && make smoke-test` on a fresh kind cluster
(Docker Desktop 4 GB, kind 0.33, kindest/node v1.37.0), 2026-09-24:

| Step | Result |
|---|---|
| `make local-up` | **PASS** — image built and pushed by digest, cluster + Cilium, `helm install` deployed on the first try: `bucket-init` hook complete in 21 s (`{"bucket": "bronze", "created": true, "object_lock": true, "versioning": true}`, `{"bucket": "bronze-replica", "created": true, "object_lock": false, "versioning": false}`), `migrate` (0001 … 0007) and `smoke` hooks complete; egress 3/3 (capture → OTE 302; metadata and cluster ranges blocked; process → OTE blocked) |
| `make smoke-test` | **PASS** — smoke hook re-run, `gaps` + freshness row written, `energy_platform_freshness_age_seconds{target="ote_intraday_market"}` present, restore-drill dry run |
| `make rollback-drill` | **PASS** — both phases (failing smoke, failing storage probe): upgrade failed as expected, release `deployed` after rollback, values restored, schema at `0007_reader_role`, 624 runs and 33 CronJobs unchanged, no throwaway schema left |
| the store-A control, live | one `capture-ceps-load` Job run by hand: `bronze/blobs/cf/cf00cd0c…` in RustFS A has `ObjectLockMode: COMPLIANCE`, `RetainUntil` = +1 day (`values-local.yaml`), and `delete-object --version-id` answers **`AccessDenied`**; bucket A reports `ObjectLockEnabled: Enabled`, versioning `Enabled` |
| Grafana on kind (the check Phase 11 owed) | `port-forward svc/energy-platform-grafana`: `/api/health` ok (12.2.0); anonymous `/api/search` → **401**; datasource `energy-platform Silver` health "Database Connection OK" through the read-only role; both dashboards provisioned |
| pods after the drill | Postgres, RustFS A and B, exporter, Grafana running; hooks completed; the two `Error` pods are the drill's deliberately failed `smoke` and `storage-probe` hooks, kept for inspection by design |

One observation, unchanged from MinIO: the WAL backups written by rclone (`backups/postgres/…`)
carry no per-object lock, because the local bucket has Object Lock **enabled** but no default
retention rule (the demo's Terraform sets one, ADR-036 §1); the platform's own PUTs are the
ones the control protects, and the drill restores from those backups either way. The cluster
was torn down after the run (`make local-down`); the capture CronJobs would otherwise keep
fetching live every 15 minutes.
