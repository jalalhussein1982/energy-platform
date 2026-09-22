# Plan — Phase 5: Deployment, IaC, HA, DR, observability (2026-09-22)

> **For agentic workers:** execute task by task. One task = one commit, `make check` green before
> each commit (03 §0). Steps use `- [ ]` checkboxes. Everything in this phase is a platform
> commit on `main`. Level 3 actions (`terraform apply`, bucket deletion, pushing a remote, the
> demo deploy itself) are listed as **author tasks** and never executed by the agent.

| | |
|---|---|
| Goal | Reproducible by the evaluator (`make local-up && make smoke-test` from a clean clone), resilient by the ADR-004 invariants (hooks, drills, replication, restore), measurable by ADR-012 (freshness SLI, alerts, dashboard). Stop when all gates pass. |
| Spec | `docs/03-roadmap.md` Phase 5; ADR-001 (amend), ADR-002, ADR-003 rev., ADR-004, ADR-012, ADR-015, ADR-016, ADR-021, ADR-024, ADR-025, ADR-026, ADR-028, ADR-033; `00` §5 V-4 … V-14 (V-12 … V-14 CONFIRMED 2026-09-22 — the Phase 5 gate is open); the starter prompt in `docs/progress.md`. |
| Architecture | Three D-* ADRs first (ADR-035 own-cluster stack, ADR-036 object stores and backups per profile, ADR-037 freshness SLI = the written form of ADR-012). Then the library gains the verbs the chart needs (`recapture`, `smoke`, `storage-probe`, `freshness`, `restore-drill`, S3 Bronze from the environment). Then one Helm chart (`tenant`-clean core, flags for everything cluster-level), the local profile on kind + Cilium, Terraform modules with two roots, tenant values for the demo, drills, observability. |
| Tech | Helm 4.3 (local; CI installs the same), kind 0.33 + Cilium (policy-enforcing CNI; kindnet does not enforce `NetworkPolicy`), Terraform ≥ 1.8 or OpenTofu 1.12 (`make` picks whichever exists; `terraform test` with `mock_provider`), `rclone` (official image by digest) for replication, tiering and backup shipping, `postgres:16` official image by digest, `postgres_exporter` by digest for metrics, `hcloud` + `aws` (Hetzner S3 endpoint) + `oci` Terraform providers. **No new Python dependency.** |
| Do not | Apply Terraform. Delete or empty a bucket. Leave a release on the reference cluster. Put an LLM in the chart's critical path. Require credentials for the local profile. Edit docs/00, 01, 02 (reconciliation edits go through the ADRs' consequences sections and the `00` §6 checklist). Weaken a gate. Push to any remote. |

## Global constraints (copied from the spec)

- Core chart = `tenant`-clean: **no CRDs**, every pod `restricted`-PSS-clean (`runAsNonRoot`,
  `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`),
  requests **and** limits on every container, images by **digest** only (05 C-43, C-44).
- Anything cluster-level lives behind a values flag (`postgres.mode=cnpg`, `metrics.operator.enabled`,
  `secrets.eso.enabled`, `egress.fqdnPolicy`) and never in the default render.
- One `CronJob` template rendered per target from `targets/*/manifest.yaml` (capture, process,
  correction per ADR-033), `concurrencyPolicy: Forbid`, gap-detector `CronJob`, hook chain per
  ADR-025 (`migrate` −10 `post-install,pre-upgrade`; `storage-probe` −5 `post-install,post-upgrade`
  only when `bronze.tiering.mode=lifecycle`; `smoke` 0 `post-install,post-upgrade,test`).
- Every deploy Make target runs `helm upgrade --install --atomic --wait --timeout`.
- NetworkPolicies per ADR-026 layer 1: default deny; DNS, Postgres, object store; TCP 443 to
  public ranges with private/metadata `except` blocks for capture, backfill and recapture pods only.
- Demo (ADR-028, V-12/V-13/V-14): store A Hetzner Object Storage with **Object Lock** and
  `bronze.tiering.mode` ∈ {`none`, `move`}, never `lifecycle`; store B OCI with a **retention
  rule and versioning OFF**; S3 client signs the whole payload (no `aws-chunked`); k3s config sets
  `anonymous.enabled: false` explicitly; server type **`cx23`** (`cx22` no longer exists);
  `residency: DE`; Hetzner €25/month and OCI €10/month ceilings in the README before any apply.
- CI workflows only call Make (ADR-015). Unit tests never open a socket (ADR-027).
- Every migration has a real downgrade (ADR-016 §3). Timezones aware everywhere.

## Decisions taken by this plan (formalisations, not new policy)

| # | Decision | Why |
|---|---|---|
| P5-D1 | **D-4 needs no new ADR**: ADR-031 (2026-09-20) already resolved it; the roadmap line "ADRs for D-1, D-3, D-4" predates it. Phase 5 writes ADR-035 (D-1 stack details), ADR-036 (D-3 per profile + backup tooling), ADR-037 (ADR-012 written: freshness SLI). | 02 §4.2 D-4 marks ADR-031; ADR-012 is "locked in principle, unwritten" and the observability deliverable needs its written form. |
| P5-D2 | **Platform image** `deployment/image/Dockerfile` (python 3.12-slim by digest, uv by digest, no dev group, uid 10001, `energy_platform/` + `targets/` + `alembic` migrations inside, entrypoint `python -m energy_platform.cli`). `make image` builds it; `make image-digest` prints `repo@sha256:…` after `kind load` / a push. The chart renders `{{ .Values.image.repository }}@{{ .Values.image.digest }}` and refuses a missing digest in `values.schema.json`. | ADR-016 §1 digest-only; the sandbox image is a different artefact (MCP, no shell). |
| P5-D3 | **Targets reach the chart as values, generated at deploy time**: `scripts/render_target_values.py targets/` emits `targets: [{id, cron, timezone, correction: {cron, days} \| null}]`; every deploy Make target and `helm-lint` pass it with `-f`. Nothing generated is committed, so a target PR still touches only `targets/<id>/`. The generator **refuses** a manifest whose `license` (lower-cased, stripped) starts with `restricted` (P4-D11 rule; 05 row C-55). | Helm cannot read outside the chart directory; "rendered once per target from `targets/*/manifest.yaml`" (ADR-003 rev.) stays literally true at deploy time. |
| P5-D4 | **Bronze from the environment** in the CLI: `ENERGY_PLATFORM_BRONZE=dir\|s3` (default `dir`); s3 reads `ENERGY_PLATFORM_S3_ENDPOINT`, `_S3_BUCKET`, `_S3_REGION`, `_S3_ALLOWED_HOSTS` (comma list), `_S3_ALLOW_INSECURE`, `_S3_RETENTION_MODE`/`_S3_RETENTION_DAYS`, credentials by secretRef name `BRONZE` (`BRONZE_ACCESS_KEY_ID`, `BRONZE_SECRET_ACCESS_KEY`); optional cold store with the `_S3_COLD_*` prefix and secretRef `BRONZE_COLD`. One function `bronze_from_env(environ) -> Bronze` in `energy_platform/bronze/config.py`, unit-tested with the fake S3 gateway. | ADR-032 backend exists; the chart maps a `Secret` to exactly these names; no new config file format. |
| P5-D5 | **New verbs**, all in the library with the CLI as a thin client (ADR-000): `recapture --days N` (ADR-033 §3: last run of each of the previous N delivery days, `force=True`); `smoke --fixture DIR` (ADR-025: capture the fixture, process, assert one ledger row `processed` and ≥ 1 Silver row, exit 1 otherwise); `storage-probe` (ADR-021 §3: `PUT` one object with the configured storage class, `HEAD` must report it; `400 InvalidArgument` or `STANDARD` → exit 1); `freshness` (ADR-037: classify each target per 01 §5 and write `target_freshness`); `restore-drill` (ADR-024 §2 + ADR-021 §5: migrate a scratch DSN, `reconcile` over the full history read from the **replica** Bronze, `replay` everything, compare counts and a checksum against the live DSN; `--dry-run` = plan the drill and check reachability only). | Each is a Phase 5 deliverable named by an ADR; hooks and CronJobs call verbs, never scripts. |
| P5-D6 | **`process` treats a forced attempt with `content_changed = true` as pending** (ADR-033 consequence); one crash-matrix row is added to `tests/runtime`. | The correction CronJob is useless otherwise. |
| P5-D7 | **Migration `0003_freshness`**: table `target_freshness(target_id PK, computed_at, partition_start, expected_by, status ∈ {pending, partial, late, complete}, observed_periods, expected_periods, newest_delivery_start, last_capture_at, last_capture_outcome, stale_fetch_streak, source_unavailable bool, pipeline_failed bool)`, one row per target, upserted by `freshness`; downgrade drops it. | ADR-012: SLI = age of the newest observation relative to expected publication; `source_unavailable` vs `pipeline_failed` are separate fields. |
| P5-D8 | **Metrics without a long-running Python process**: the gap-detector CronJob runs `gaps` then `freshness`; a `metrics` Deployment runs `postgres_exporter` (image by digest) with a queries ConfigMap over `target_freshness`, `runs` and `run_attempts`, exposing `energy_platform_freshness_age_seconds{target}`, `energy_platform_freshness_status{target,status}`, `energy_platform_source_unavailable{target}`, `energy_platform_pipeline_failed{target}`, `energy_platform_runs{target,state}`. `/metrics` + `prometheus.io/*` annotations by default; `PodMonitor` + `PrometheusRule` only behind `metrics.operator.enabled`; the same rules ship as a plain ConfigMap for operator-less scrapers; Grafana dashboard JSON in `deployment/helm/energy-platform/dashboards/`. | D-6 (annotations default, operator behind flag); `http.server` is a banned import outside `fetch/` (ADR-027) and the exemption list is a negative test — no exporter is written in Python. |
| P5-D9 | **Postgres in the chart**: `postgres.mode=statefulset` = one `StatefulSet` on the official `postgres:16` image by digest, `runAsUser/fsGroup 999`, `PGDATA` in a subdirectory, `archive_mode=on` with `archive_command` copying WAL to a shared `wal-archive` volume; `cnpg` = a `Cluster` CR rendered only behind the flag; `external` = a DSN `Secret` by name. Backups (ADR-036): `pg-backup` CronJob = init container `pg_basebackup` (postgres image) + `rclone` container shipping base + `wal-archive` to `bronze.backupPrefix` on store A; replication mirrors it to B. `cnpg` mode delegates to CNPG's own object-store backup; `external` documents the provider's PITR. | ADR-002 names pgBackRest/WAL-G; both need a custom Postgres image with the binary inside. Base backup + WAL archive shipped by the tool the design already uses (`rclone`) gives PITR with no new image build; ADR-036 records the amendment and the drill proves it. |
| P5-D10 | **Local profile**: kind single node (8 GB laptop), `disableDefaultCNI: true`, Cilium by Helm (pinned chart version, `image.useDigest=true`, `policyEnforcementMode=default`), `objectstore.local.enabled=true` renders two MinIO StatefulSets (image by digest) and a `minio-init` Job (`mc` by digest) creating bucket A `--with-lock` and bucket B plain; local secrets are **generated** by `make local-up` into one `Secret` (`energy-platform-local`) the chart consumes by name (`secrets.existingSecret`); SOPS is documented as the way to produce the same `Secret` shape from an encrypted file, not required. The platform image is built locally and loaded with `kind load docker-image`; the digest is read back from the node (`crictl inspecti`), so the rendered manifests still carry `@sha256:`. | ADR-010 offline reproduction; roadmap "do not require credentials for the local profile"; ADR-026 §4 CNI requirement. |
| P5-D11 | **Terraform layout**: `deployment/own-cluster/terraform/modules/{network,nodes,storage,security}`, `cloud-init/k3s-server.yaml.tftpl`, `k3s-agent.yaml.tftpl`, `authn.yaml.tftpl`; roots `roots/openstack` (mock-tested; ≤ 3 × e1.large, one network, one floating IP) and `roots/hcloud` (2 × `cx23`, private network, firewall 443/tcp from `0.0.0.0/0` + 6443/tcp from `var.admin_cidr`, one volume for Postgres; `storage` module manages bucket A over the `aws` provider against the Hetzner endpoint — versioning + Object Lock — and bucket B over the `oci` provider with a retention rule and versioning disabled). `terraform test` with `mock_provider` for both roots; the Makefile iterates over roots and uses `terraform` or `tofu`, whichever exists (CI runners ship `terraform`). Plans go to `~/.config/energy-platform/plans/`, outside the repository. | ADR-028 §2 layout; V-14 facts (structured authn, `anonymous.enabled: false`, `cx23`); V-12/V-13 controls; CLAUDE.md Level 3. |
| P5-D12 | **Deploy identity for the demo**: `.github/workflows/deploy-demo.yml` (`workflow_dispatch` + `push` to `main` once the author enables it), `permissions: id-token: write`, one step `make deploy-demo`; `scripts/kubeconfig_from_oidc.sh` builds the kubeconfig from the runner's ID token (audience `energy-platform-demo`) and the public cluster CA (`DEMO_CLUSTER_URL`, `DEMO_CLUSTER_CA` repository variables). **Blocked on the author**: this checkout has no GitHub remote; the cluster does not exist until `terraform apply`. The agent delivers the workflow, the Make target, the script and the values; the author runs the rest. | ADR-015 federation clause, V-14; CLAUDE.md Level 3. |
| P5-D13 | **Rollback drill** = `make rollback-drill` (kind): deploy revision N (fixture smoke passes) → N+1 with `smoke.fixture` pointing at a fixture from a **different target** (the parser cannot produce a Silver row → smoke fails → `--atomic` rolls back) → assert `helm history` shows N deployed, `alembic current` unchanged, Bronze captures of the failed smoke present in the capture log and reconciled into the ledger; then N+1 with `bronze.tiering.mode=lifecycle`, `storageClass=COLD` against MinIO (reports `STANDARD`) → the `storage-probe` hook fails → same assertions. `.github/workflows/weekly-drills.yml` (`schedule` + `workflow_dispatch`) runs it on a kind cluster in CI. | ADR-016 §6, ADR-025 §5 (a) and (b) without shipping a deliberately broken image. |
| P5-D14 | **Restore drill** = `drills.restore` CronJob in the chart: pod with a scratch Postgres sidecar (native sidecar, `restartPolicy: Always` init container), init container `rclone` pulling the newest base backup + WAL from store **B**, `pg_ctl` recovery, then `energyctl restore-drill --scratch-dsn … --replica` (reads Bronze from B, reconcile over the full history, replay, compare with live). `--dry-run` in `make smoke-test`. | ADR-002 restore drill; ADR-024 §2 ledger rebuild; ADR-021 §5 cold-backed replay; ADR-028 §3 "restore drill reads from B". |
| P5-D15 | **Cost guard**: `deployment/own-cluster/README.md` states the ceilings (Hetzner €25/month, OCI €10/month), what runs (2 × cx23 ≈ €8, one 10 GB volume, Object Storage at demo volume, OCI within the free 20 GB) and the author's checklist (budget alerts in both consoles, `terraform apply`, bucket creation is Terraform's, deletion never). | ADR-028 §5. |
| P5-D16 | **Third-party images by digest**, resolved once with `docker buildx imagetools inspect` and written into `values.yaml` with the tag they were resolved from as a comment: `postgres:16`, `minio/minio`, `minio/mc`, `rclone/rclone`, `quay.io/prometheuscommunity/postgres-exporter`, `curlimages/curl` (egress test only, `deployment/local/`). Cilium's chart pins its own digests (`image.useDigest`). | 05 C-43 on rendered output; ADR-016 §1. |
| P5-D17 | **`helm-lint` gate** = `helm lint` + `helm template` with tenant values **and** with local values **and** with every flag on (`cnpg`, `operator`, `eso`, `fqdnPolicy`), each render piped through `scripts/check_workloads.py` and the new `scripts/check_restricted_pss.py`; `tests/harness/test_restricted_pss.py` carries the negative tests (root user, missing seccomp, privilege escalation, capabilities not dropped, host namespace). The default render is asserted to contain **no** CRD-backed kind (05 row C-56). | 05 §2 row for `helm-lint`; ADR-001 amend rule 2 and 3. |
| P5-D18 | **V-11 stays open**; the tenant README says "layer 1 declared, enforcement unverified on the reference cluster" until the author runs the one-off probe. The demo cluster (k3s embedded policy controller) is where layer 1 is verified for real by the same egress test Job as the local profile. | ADR-026 §4; ADR-028 §2. |

## File structure

```text
deployment/
├── image/Dockerfile                          # platform runtime image (P5-D2)
├── helm/energy-platform/
│   ├── Chart.yaml  values.yaml  values.schema.json  README.md
│   ├── dashboards/freshness.json             # Grafana (P5-D8)
│   └── templates/
│       ├── _helpers.tpl  serviceaccount.yaml  secret.yaml (existingSecret or eso)
│       ├── cronjob-target.yaml               # capture + process + correction, per target (P5-D3)
│       ├── cronjob-gaps.yaml                 # gaps + freshness
│       ├── cronjob-tier.yaml  cronjob-replicate.yaml  cronjob-pg-backup.yaml  cronjob-restore-drill.yaml
│       ├── hook-migrate.yaml  hook-storage-probe.yaml  hook-smoke.yaml
│       ├── postgres-statefulset.yaml  postgres-cnpg.yaml  postgres-service.yaml
│       ├── minio.yaml  minio-init-job.yaml   # objectstore.local.enabled only
│       ├── metrics-deployment.yaml  metrics-configmap.yaml  metrics-service.yaml
│       ├── podmonitor.yaml  prometheusrule.yaml  alerts-configmap.yaml
│       ├── networkpolicy-default-deny.yaml  networkpolicy-common.yaml  networkpolicy-egress-capture.yaml  ciliumnetworkpolicy.yaml
├── local/
│   ├── kind-config.yaml  cilium-values.yaml  values-local.yaml  egress-test-job.yaml  README.md
│   └── drills/rollback.sh
├── tenant/
│   ├── values-tenant.yaml  values-demo.yaml  README.md
└── own-cluster/
    ├── README.md  values-own-cluster.yaml
    └── terraform/
        ├── modules/{network,nodes,storage,security}/{main,variables,outputs}.tf
        ├── cloud-init/{k3s-server.yaml.tftpl,k3s-agent.yaml.tftpl,authn.yaml.tftpl}
        └── roots/{openstack,hcloud}/{main,variables,outputs,providers}.tf + tests/*.tftest.hcl
energy_platform/
├── bronze/config.py                          # bronze_from_env (P5-D4)
├── runtime/{recapture,smoke,probe,freshness,drill}.py
├── silver/migrations/versions/0003_freshness.py
└── cli.py                                    # recapture, smoke, storage-probe, freshness, restore-drill
scripts/
├── render_target_values.py  check_restricted_pss.py  kubeconfig_from_oidc.sh
.github/workflows/{ci.yml (helm-lint, terraform-validate unchanged names), deploy-demo.yml, weekly-drills.yml}
docs/adr/ADR-035-own-cluster-stack.md  ADR-036-object-stores-and-backups-per-profile.md  ADR-037-freshness-sli.md
docs/07-operations.md                         # deploy, drills, restore, rollback runbook
```

## Ordered tasks

### Task 5.1 — Plan and the D-* ADRs

**Files:** this file; `docs/adr/ADR-035-own-cluster-stack.md`; `docs/adr/ADR-036-object-stores-and-backups-per-profile.md`; `docs/adr/ADR-037-freshness-sli.md`; `docs/02-architecture-decisions.md` ADR index rows and §4.2 D-1/D-3 pointers, ADR-012 pointer (reconciliation edits only, per `00` §6 practice); `docs/03-roadmap.md` Phase 5 first bullet reworded (D-4 already ADR-031).

- [ ] ADR-035 ACCEPTED (D-1): k3s over cloud-init on plain VMs, two roots over four modules, the k3s config (structured `authentication-config` trusting the GitHub Actions issuer, `anonymous.enabled: false` explicit, embedded NetworkPolicy controller, Traefik disabled, `--secrets-encryption`), `cx23`, the firewall shape, why not Magnum/OKE/RKE2, mock-tested in CI, applied by the author only.
- [ ] ADR-036 ACCEPTED (D-3 + amends ADR-002 backup tooling): per-profile store table (local MinIO ×2; demo A Hetzner Object Lock + versioning, `tiering.mode ∈ {none, move}`; demo B OCI retention rule + versioning OFF; reference RGW/Swift stays the record), whole-payload signing, storage probe by `PUT`, replication `rclone` CronJob A → B (`--immutable`-style: copy, never delete, checksum check), Postgres backup per `postgres.mode` (P5-D9), restore drill reads B, what the restore drill asserts.
- [ ] ADR-037 ACCEPTED (writes ADR-012): SLI definition per 01 §5, `target_freshness` table, `freshness` verb in the gap-detector run, `postgres_exporter` exposure, metric names, alert rules (`late` for > 2 cadences; `pipeline_failed`; `source_unavailable` is a warning, not an incident), dashboard.
- [ ] `02` ADR index gains three rows; §4.2 D-1 and D-3 gain "resolved by ADR-035 / ADR-036"; ADR-012 heading gains "(written 2026-09-22 as ADR-037)". `03` Phase 5 first bullet: "ADRs for D-1, D-3 (D-4 was resolved by ADR-031); ADR-012 written as ADR-037".
- [ ] `make check` green. Commit `docs(phase-5): plan, ADR-035 (own-cluster stack), ADR-036 (object stores and backups per profile), ADR-037 (freshness SLI)`.

**Acceptance:** three ADR files exist with every section of the template filled; `02` index lists them; `make check` green.

### Task 5.2 — Library: Bronze from the environment, `recapture`, `smoke`, `storage-probe`

**Files:** `energy_platform/bronze/config.py` (new), `energy_platform/runtime/recapture.py`, `energy_platform/runtime/smoke.py`, `energy_platform/runtime/probe.py` (new), `energy_platform/runtime/process.py` (P5-D6), `energy_platform/runtime/__init__.py`, `energy_platform/cli.py`, `tests/bronze/test_config.py`, `tests/runtime/test_recapture.py`, `tests/runtime/test_smoke.py`, `tests/runtime/test_probe.py`, `tests/runtime/test_process.py` (one crash-matrix row), `tests/cli/…`.

- [ ] `bronze_from_env(environ: Mapping[str, str], *, transport=None) -> Bronze` per P5-D4; `dir` default; `s3` builds `ObjectStore`/`S3BlobStore`/`S3CaptureLog` (and a cold store when `_S3_COLD_ENDPOINT` is set); unknown mode → `ValueError`; tests use `tests/fetch/fake_s3.py`. The CLI's `_bronze()` calls it when `--bronze-dir` is not given.
- [ ] `recapture(rt, *, days, now)`: for each of the previous `days` delivery days (source tz), find the last run (`store.runs` by window or the capture log's `latest` per day) and call `capture(rt, scheduled_for=…, force=True)`; returns the reports; a day with no run is skipped and reported. Test: three days, two with runs → two forced captures with attempt numbers incremented; `content_changed` propagated.
- [ ] `process`: a run whose newest attempt is a forced capture with `content_changed=True` and outcome `NULL` is pending → claimed and processed (P5-D6). Test row in the crash matrix.
- [ ] `smoke(rt, fixture_dir) -> SmokeReport(ok, run_state, silver_rows, message)`; CLI `energyctl smoke --manifest … --fixture …` exits 1 when `not ok`. Tests: pass on the T1 ordinary-day fixture with `MemoryStore`; fail on a fixture of another target (rows = 0); fail when the database is unreachable (`UnavailableStore`).
- [ ] `storage_probe(store: ObjectStore, storage_class: str) -> ProbeReport`; CLI `energyctl storage-probe` reads the S3 env of P5-D4 plus `ENERGY_PLATFORM_S3_STORAGE_CLASS`; the object key is `probe/<uuid>` and is deleted only when `allow_delete` (it is not: the key stays, documented). Tests with the fake gateway: class echoed → ok; `400 InvalidArgument` (empty `<Message></Message>`, V-12) → fail; `HEAD` says `STANDARD` → fail. The S3 client must tolerate the empty `Message` (V-12 note) — test it.
- [ ] Commit `feat(runtime): Bronze from the environment, recapture (ADR-033), smoke and storage-probe verbs (ADR-021, ADR-025)`.

**Acceptance:** `make check` green; `energyctl recapture|smoke|storage-probe --help` render; tests offline.

### Task 5.3 — Freshness SLI (ADR-037): migration 0003 and the `freshness` verb

**Files:** `energy_platform/silver/migrations/versions/0003_freshness.py`, `energy_platform/store/protocol.py` (+ `upsert_freshness`, `freshness_rows`), `energy_platform/store/memory.py`, `energy_platform/store/postgres.py`, `energy_platform/runtime/freshness.py`, `energy_platform/cli.py` (`freshness`, and `gaps --with-freshness`), `tests/runtime/test_freshness.py`, `tests/store/test_store_suite.py` (both backends), `docs/04-contracts.md` §6 rows.

- [ ] Migration with a real downgrade; `make migration-check` and `make db-test` round trip green.
- [ ] `compute_freshness(rt, now) -> Freshness`: partition = delivery day (T1/T2/E1) or delivery hour (T3) per the registry's resolution; `expected_periods` from `local_day_intervals`; `observed_periods` = distinct `delivery_start` in `observations_current` for the partition; status per 01 §5 (`pending` before the cadence's first instant of the partition; `complete` when observed = expected; `late` when `now > expected_by` = the last cadence instant of the partition + 2 × cadence (ADR-031 tolerance); else `partial`); `last_capture_*` from the capture log; `stale_fetch_streak` = consecutive `content_changed=False`; `source_unavailable` = last attempt error is a fetch error (`fetch_error`, `http_5xx`, `timeout`); `pipeline_failed` = last attempt error is anything else. Property test: DST days (92/100 expected).
- [ ] Commit `feat(freshness): target_freshness table and the freshness verb (ADR-037 / ADR-012)`.

**Acceptance:** `make check`, `make db-test` green; `energyctl freshness --manifest …` prints one JSON row.

### Task 5.4 — `restore-drill` verb (ADR-024 §2, ADR-021 §5, ADR-002)

**Files:** `energy_platform/runtime/drill.py`, `energy_platform/cli.py`, `tests/runtime/test_drill.py`.

- [ ] `restore_drill(live: Store, scratch: Store, replica: Bronze, manifests, *, now, dry_run) -> DrillReport`: `dry_run` lists the targets, counts capture-log entries in the replica and checks `scratch.ping()`; full run = `reconcile` over the full history (window = everything), `replay_range` over every run, then compare per target: `runs` count by state, `observations_current` row count and an order-independent SHA-256 over `(observation identity, value)` between live and scratch; `ok` iff equal; RTO measured as wall clock and reported.
- [ ] CLI `energyctl restore-drill --scratch-dsn … [--dry-run]` with the replica Bronze from `ENERGY_PLATFORM_S3_REPLICA_*` (same shape as P5-D4, secretRef `BRONZE_REPLICA`) and the live DSN from `ENERGY_PLATFORM_DSN` (read-only use).
- [ ] Tests with `MemoryStore` ×2 and a memory Bronze seeded through the fixture path: identical → ok; a Silver row missing in scratch → not ok with the differing target named; dry-run never writes.
- [ ] Commit `feat(drill): restore-drill verb rebuilding the ledger and Silver from the replica Bronze (ADR-024 §2, ADR-021 §5)`.

### Task 5.5 — Platform image

**Files:** `deployment/image/Dockerfile`, `Makefile` (`image`, `image-digest`, `IMAGE_REPO ?= energy-platform`, `IMAGE_TAG ?= dev`), `.dockerignore`, `tests/harness/test_workloads.py` (the new Dockerfile is scanned by `scan()`), `docs/07-operations.md` §1 (image build and digest).

- [ ] Dockerfile per P5-D2 (two `FROM` by digest, `uv sync --frozen --no-dev`, `COPY energy_platform targets pyproject.toml uv.lock README.md alembic.ini`), `USER 10001:10001`, `ENTRYPOINT ["/app/.venv/bin/python", "-m", "energy_platform.cli"]`, `HEALTHCHECK NONE`.
- [ ] `make image` = `docker build -f deployment/image/Dockerfile -t $(IMAGE_REPO):$(IMAGE_TAG) .`; `make image-digest` prints the `RepoDigests` entry or, with `KIND=1`, the digest from the kind node (`docker exec <node> crictl inspecti --output go-template …`).
- [ ] `make workload-check` green (Dockerfile pins). Build succeeds locally: `docker run --rm energy-platform:dev --help` prints the verbs.
- [ ] Commit `feat(image): platform runtime image by digest (ADR-016 §1)`.

### Task 5.6 — Helm chart core and the `helm-lint` gate

**Files:** everything under `deployment/helm/energy-platform/` except drills/metrics/backup templates (Tasks 5.10–5.12 add theirs), `scripts/render_target_values.py`, `scripts/check_restricted_pss.py`, `tests/harness/test_render_target_values.py`, `tests/harness/test_restricted_pss.py`, `tests/harness/test_chart.py` (renders the chart with `helm template` **only when `helm` is on PATH**, else `pytest.skip` with the reason; CI has helm), `Makefile` (`helm-lint` real, `HELM_TARGET_VALUES` recipe), `docs/05-constraint-matrix.md` (rows C-55 restricted license refused by the renderer, C-56 no CRD-backed kind in the default render, C-57 pod not restricted-PSS-clean; §2 `helm-lint` row), `deployment/helm/energy-platform/README.md`.

- [ ] `render_target_values.py`: loads every `targets/*/manifest.yaml` through `load_manifest`, emits the P5-D3 document to stdout; refuses `restricted` licences (exit 1, names the target); test with `targets_builder`.
- [ ] `check_restricted_pss.py`: for every Pod-bearing kind, pod-level `securityContext.runAsNonRoot: true` and `seccompProfile.type: RuntimeDefault` (or on every container), every container `allowPrivilegeEscalation: false`, `capabilities.drop == [ALL]`, no `privileged`, no `hostNetwork/hostPID/hostIPC`, no `hostPath` volume, no `hostPort`; exit 1 with the path of the offending field. Negative tests per rule.
- [ ] Chart: `Chart.yaml` (apiVersion v2, `kubeVersion: ">=1.29.0"`), `values.yaml` with these top-level keys and no others: `image`, `targets` (empty by default; filled by the generator), `schedule` (`startJitterSeconds`, `startingDeadlineSeconds`, history limits), `postgres` (`mode`, `dsnSecretRef`, `storageClassName`, `size`, `image`), `bronze` (`endpoint`, `bucket`, `allowedHosts`, `allowInsecure`, `retention`, `tiering {mode, afterDays, storageClass, coldEndpoint, coldBucket}`, `replica {endpoint, bucket, allowedHosts}`, `backupPrefix`), `objectstore.local` (`enabled`, MinIO images), `secrets` (`existingSecret`, `eso {enabled, storeRef}`), `metrics` (`enabled`, `operator {enabled}`, exporter image), `egress` (`privateCIDRs`, `clusterCIDRs`, `postgresCIDRs`, `objectStoreCIDRs`, `fqdnPolicy`), `drills` (`restore {enabled, schedule}`), `smoke` (`manifest`, `fixture`), `residency`, `resources` (per role), `podAnnotations`. `values.schema.json` makes `image.digest` (`^sha256:[0-9a-f]{64}$`), `bronze.endpoint`, `bronze.bucket`, `residency` required and enumerates `postgres.mode`, `bronze.tiering.mode`, `egress.fqdnPolicy`.
- [ ] Templates: `_helpers.tpl` (labels, `image` helper that fails on a missing digest, `securityContext` helpers, `bronzeEnv` helper mapping values → the P5-D4 env names, `secretRef` helper), `serviceaccount.yaml` (`automountServiceAccountToken: false`), `secret.yaml` (renders an `ExternalSecret` only when `secrets.eso.enabled`; otherwise nothing — the `Secret` is pre-existing by name), `cronjob-target.yaml` (range over `.Values.targets`: `capture-<id>`, `process-<id>`, `recapture-<id>` when `correction` is set; `concurrencyPolicy: Forbid`; `startingDeadlineSeconds`; jitter via `sleep $((RANDOM % jitter))` is **not** allowed (no shell in the image) → jitter is a CLI flag `--start-jitter-seconds` on `capture` that sleeps in-process; labels `energy-platform.io/role`), `cronjob-gaps.yaml` (one container running `energyctl gaps --with-freshness`: gap detection, then the freshness row), `hook-migrate.yaml`, `hook-storage-probe.yaml` (only when `tiering.mode=lifecycle`), `hook-smoke.yaml` (`post-install,post-upgrade,test`, weight 0, `hook-delete-policy: before-hook-creation,hook-succeeded`), `postgres-statefulset.yaml` (+ headless `Service`, PVC, `wal-archive` PVC, `postgresql.conf` ConfigMap with `archive_mode=on`), `postgres-cnpg.yaml` (behind `mode=cnpg`), `minio.yaml` + `minio-init-job.yaml` (behind `objectstore.local.enabled`; `mc mb --with-lock` for A, plain for B, `mc version enable` on A), NetworkPolicies (P5-D8 shape; `ipBlock` values for external Postgres/object store; `ciliumnetworkpolicy.yaml` behind `egress.fqdnPolicy=cilium` using the host registry hosts passed by the generator as `hosts:`).
- [ ] `make helm-lint` per P5-D17; `tests/harness/test_chart.py` asserts: default render has no `CustomResourceDefinition`, `Cluster`, `PodMonitor`, `ExternalSecret`, `CiliumNetworkPolicy`; a target with `correction` renders three CronJobs, without it two; every CronJob has `concurrencyPolicy: Forbid`; only `capture-*`, `recapture-*` and `backfill` pods match the 443 egress policy; every pod passes `check_restricted_pss`.
- [ ] Commit `feat(helm): energy-platform chart — per-target CronJobs, ADR-025 hook chain, postgres modes, NetworkPolicies, restricted-PSS gate (ADR-001, ADR-003 rev., ADR-025, ADR-026)`.

**Acceptance:** `make helm-lint` green locally (helm 4.3) with tenant, local and all-flags renders; `make check` green.

### Task 5.7 — Local profile: `make local-up`, egress test, `make local-down`

**Files:** `deployment/local/{kind-config.yaml, cilium-values.yaml, values-local.yaml, egress-test-job.yaml, README.md}`, `Makefile` (`local-up`, `local-down`, `deploy-local`, `local-secrets`, `local-egress-test`, `CILIUM_VERSION`, `KIND_NODE_IMAGE` by digest), `docs/07-operations.md` §2.

- [ ] `kind-config.yaml`: one control-plane node, node image by digest, `disableDefaultCNI: true`, `kubeProxyMode: iptables`, `podSubnet`/`serviceSubnet` fixed (they feed `egress.clusterCIDRs`).
- [ ] `make local-up`: `kind create cluster --config` (idempotent) → `helm upgrade --install cilium cilium/cilium --version $(CILIUM_VERSION) -f cilium-values.yaml --wait` (`policyEnforcementMode=default`, `image.useDigest=true`, resources set) → `make image && kind load docker-image` → `make local-secrets` (random Postgres password and MinIO keys with `openssl rand -hex`, `kubectl create secret generic energy-platform-local --dry-run=client -o yaml | kubectl apply`) → `make deploy-local` = `helm upgrade --install energy-platform $(CHART_DIR) -n energy-platform --create-namespace -f deployment/local/values-local.yaml -f <(python -m scripts.render_target_values targets) --set image.digest=$(make -s image-digest KIND=1) --atomic --wait --timeout 10m` (hooks: `migrate`, `smoke`) → `make local-egress-test`.
- [ ] `egress-test-job.yaml` (curl image by digest, restricted PSS, requests/limits): three Jobs with the labels of a capture pod / a process pod: capture pod → `https://www.ote-cr.cz` 200 or 301 (network needed: the Make target says so and skips the assertion offline with `LOCAL_EGRESS_OFFLINE=1`, never fakes it); capture pod → `http://169.254.169.254` and `http://10.0.0.1` → connection refused/timeout (exit 7/28 expected); process pod → `https://www.ote-cr.cz` → blocked.
- [ ] `make local-down` = `kind delete cluster`. README: prerequisites (Docker with ≥ 4 GB, kind, helm, kubectl), what runs, how to look at the ledger (`kubectl exec … psql`), MinIO console port-forward.
- [ ] Run it: `make local-up` green on this laptop; record wall-clock in `docs/07-operations.md`.
- [ ] Commit `feat(local): kind + Cilium profile, generated local secrets, atomic deploy with hooks, layer-1 egress test (ADR-010, ADR-026 §4)`.

**Acceptance:** from a clean clone `make local-up` ends with the smoke hook succeeded and the three egress assertions printed; `kubectl get cronjobs -n energy-platform` lists capture/process/recapture per target and `gaps`.

### Task 5.8 — Terraform: modules, two roots, mock tests, `hcloud` plan

**Files:** `deployment/own-cluster/terraform/**` per P5-D11, `deployment/own-cluster/README.md` (P5-D15 cost guard + author checklist), `deployment/own-cluster/values-own-cluster.yaml`, `Makefile` (`terraform-validate` iterates `roots/*`, `TF ?=` detection, `terraform-plan-hcloud` writing to `~/.config/energy-platform/plans/`), `.gitignore` (`*.tfstate*`, `.terraform/`, `*.tfplan`).

- [ ] Modules: `network` (private network + subnet; OpenStack: pre-provisioned network by name, one floating IP), `nodes` (server + agents from cloud-init templates; `k3s-server.yaml.tftpl` installs a pinned k3s version by checksum, writes `/etc/rancher/k3s/config.yaml` with `disable: [traefik]`, `secrets-encryption: true`, `kube-apiserver-arg: [authentication-config=/etc/rancher/k3s/authn.yaml]`, `tls-san`, and `authn.yaml.tftpl` = the V-14 `AuthenticationConfiguration` with `anonymous: {enabled: false}` explicit, JWT issuer `https://token.actions.githubusercontent.com`, audience `var.oidc_audience`, username `'gha:' + claims.repository`, claim rules on `repository` and `ref`; the namespace `Role`/`RoleBinding` for `gha:<repo>` applied by the server's manifests dir), `storage` (Postgres volume; bucket A via `aws` provider with `aws_s3_bucket_versioning` + `aws_s3_bucket_object_lock_configuration` COMPLIANCE `var.bronze_lock_days`; bucket B via `oci_objectstorage_bucket` versioning `Disabled` + `oci_objectstorage_object_lifecycle_policy`-free `oci_objectstorage_bucket` retention rule `var.replica_retention_days`), `security` (hcloud firewall 443/tcp any, 6443/tcp `var.admin_cidr`, SSH only from `var.admin_cidr`; OpenStack security groups equivalent).
- [ ] Roots: `hcloud` (2 × `cx23`, nbg1, image `ubuntu-24.04`, one 10 GB volume), `openstack` (≤ 3 × e1.large, `v3applicationcredential` auth variables). `tests/plan.tftest.hcl` per root with `mock_provider "hcloud" {}`, `mock_provider "aws" {}`, `mock_provider "oci" {}`, `mock_provider "openstack" {}` asserting server type, count, firewall rules, bucket lock/retention attributes, and that `authn.yaml` rendered content contains `enabled: false`.
- [ ] `make terraform-validate` green with `tofu` here; `make terraform-plan-hcloud` produces a plan with the author's credentials sourced from `~/.config/energy-platform/verify.env` (read-only; **never `apply`**); plan summary into `docs/07-operations.md` §3.
- [ ] Commit `feat(terraform): own-cluster modules, openstack (mock-tested) and hcloud (planned) roots, k3s structured authentication (ADR-035, ADR-028)`.

**Acceptance:** `make terraform-validate` green; plan file exists outside the repo and its summary reads 2 servers, 1 network, 1 firewall, 1 volume, 2 buckets.

### Task 5.9 — Tenant values, demo values, OIDC deploy path

**Files:** `deployment/tenant/{values-tenant.yaml, values-demo.yaml, README.md}`, `scripts/kubeconfig_from_oidc.sh`, `Makefile` (`deploy-tenant ENV=<env>`, `deploy-demo`, `kubeconfig-oidc`), `.github/workflows/deploy-demo.yml`, `tests/harness/test_ci_wrappers.py` (every workflow only calls Make — already parametrised; the new workflow's `permissions.id-token == write` and `contents == read`), `docs/07-operations.md` §4.

- [ ] `values-tenant.yaml`: `postgres.mode=statefulset`, `storageClassName` by name, `secrets.existingSecret`, `metrics.operator.enabled=false`, `bronze.tiering.mode=none`, layer-1 note in the README (P5-D18). `values-demo.yaml`: `residency: DE`, `bronze.endpoint=https://nbg1.your-objectstorage.com`, bucket names from the Terraform outputs, `bronze.retention {COMPLIANCE, days}`, `tiering.mode=none`, `replica.endpoint=https://<ns>.compat.objectstorage.eu-frankfurt-1.oraclecloud.com` (namespace value documented, not committed), `drills.restore.enabled=true` daily, `smoke.fixture` = the T1 ordinary-day fixture.
- [ ] `kubeconfig_from_oidc.sh`: requests the ID token from `ACTIONS_ID_TOKEN_REQUEST_URL` with audience `energy-platform-demo` (`curl` on the runner), writes a kubeconfig with `DEMO_CLUSTER_URL`, `DEMO_CLUSTER_CA` and the token; `make deploy-demo` = `kubeconfig-oidc` then `deploy-tenant ENV=demo` with `--namespace energy-platform`.
- [ ] Workflow: `workflow_dispatch` only (the author switches on `push: main` after the first manual run), `permissions: {id-token: write, contents: read}`, steps `make ci-bootstrap`, `make deploy-demo`.
- [ ] Author tasks recorded in the README and `docs/progress.md`: create the GitHub remote and push; set repository variables `DEMO_CLUSTER_URL`, `DEMO_CLUSTER_CA`; `terraform apply` the `hcloud` root after the budget alerts; create the `energy-platform` Secret in the namespace from the Terraform outputs; run the workflow.
- [ ] Commit `feat(tenant): tenant and demo values, GitHub OIDC deploy path to the demo cluster (ADR-015 federation clause, ADR-028, V-14)`.

**Acceptance:** `make helm-lint` renders the demo values; `make deploy-demo` fails fast and honestly without the variables ("DEMO_CLUSTER_URL unset"); the workflow passes `test_ci_workflow_only_calls_make`.

### Task 5.10 — Backups, replication, tiering, restore drill (chart + local run)

**Files:** `deployment/helm/energy-platform/templates/{cronjob-pg-backup.yaml, cronjob-replicate.yaml, cronjob-tier.yaml, cronjob-restore-drill.yaml}`, values keys already declared in 5.6, `tests/harness/test_chart.py` additions, `docs/07-operations.md` §5 (restore runbook, RPO/RTO measured).

- [ ] `cronjob-pg-backup.yaml` (P5-D9; statefulset mode only): init `pg_basebackup -D /backup/base -Ft -z -X none` (postgres image), container `rclone copy /backup <A>/<backupPrefix>/base/<timestamp>/` + `rclone copy /wal-archive <A>/<backupPrefix>/wal/` (`--immutable`, `--checksum`); rclone config from the same `Secret` (`RCLONE_CONFIG_A_*` env from the secret helper).
- [ ] `cronjob-replicate.yaml`: `rclone copy A:bucket B:bucket --checksum --immutable` (never `sync`, never delete; ADR-036), both `bronze/` and `<backupPrefix>/`, hourly by default; provider `Other` for OCI (V-13), whole-object uploads (`--s3-upload-cutoff 0` is wrong for large files → `--s3-chunk-size` default; OCI rejects `aws-chunked` only for signing, rclone's multipart is fine — verified by V-13).
- [ ] `cronjob-tier.yaml` (behind `tiering.mode=move`): ADR-021 keeps hot and cold keys identical and the Bronze read path already tries hot then cold, so the job is `rclone move A:bucket/bronze/blobs COLD:coldBucket/bronze/blobs --min-age <afterDays>d --checksum`; capture-log entries stay hot and untouched; no `tier` verb is needed in the library (documented in ADR-036).
- [ ] `cronjob-restore-drill.yaml` per P5-D14 (behind `drills.restore.enabled`): native sidecar scratch Postgres (postgres image, emptyDir), init `rclone copy B:<backupPrefix>/base/<latest>` + WAL, init `tar` + `recovery.signal` + `restore_command`, main container `energyctl restore-drill --scratch-dsn postgres://…@localhost/… ` with `ENERGY_PLATFORM_S3_REPLICA_*` = store B; exits non-zero on mismatch (the Job fails → alert `energy_platform_restore_drill_failed` from `kube_job_status_failed`, documented).
- [ ] Local run: `values-local.yaml` enables backup (every 5 min), replicate (every 5 min), restore drill (every 10 min) against MinIO A → B; wait for one of each; `kubectl logs` of the restore drill shows `ok=true`, counts equal, RTO seconds; record in `docs/07-operations.md`.
- [ ] Commit `feat(dr): Postgres base+WAL backup shipping, Bronze A→B replication, move-mode tiering, restore drill CronJob (ADR-002, ADR-021, ADR-024 §2, ADR-036)`.

**Acceptance:** on kind, one backup, one replication and one restore drill run succeeded; `rclone check` between A and B reports 0 differences (from the replicate pod logs).

### Task 5.11 — Rollback drill

**Files:** `deployment/local/drills/rollback.sh`, `Makefile` (`rollback-drill`), `.github/workflows/weekly-drills.yml` (`schedule` weekly + `workflow_dispatch`; steps `make ci-bootstrap`, `make local-up`, `make rollback-drill`, `make local-down`), `tests/harness/test_ci_wrappers.py` (the drills workflow is schedule/dispatch only), `docs/07-operations.md` §6.

- [ ] `rollback.sh` per P5-D13: records `helm history` revision N, `alembic current` (via `energyctl migrate --current`), capture-log entry count; runs N+1 with the wrong fixture, expects `helm upgrade` to exit non-zero, asserts revision N is `deployed` and N+1 `failed`, schema revision unchanged, capture-log count grew by one (the failed smoke's capture) and `energyctl gaps` reconciles it (ledger row exists with `origin=reconciled`); then N+1 with `bronze.tiering.mode=lifecycle`, `storageClass=COLD` → the probe hook fails → same assertions. Every assertion prints `PASS`/`FAIL` and the script exits 1 on any FAIL.
- [ ] Run on kind; paste the transcript summary into `docs/07-operations.md`.
- [ ] Commit `feat(drills): rollback drill under --atomic with a failing smoke and a failing storage probe; weekly drills workflow (ADR-016 §6, ADR-025 §5)`.

### Task 5.12 — Observability: exporter, alert rules, dashboard

**Files:** `deployment/helm/energy-platform/templates/{metrics-deployment.yaml, metrics-configmap.yaml, metrics-service.yaml, podmonitor.yaml, prometheusrule.yaml, alerts-configmap.yaml}`, `deployment/helm/energy-platform/dashboards/freshness.json`, `tests/harness/test_chart.py` additions (PodMonitor/PrometheusRule absent by default, present with the flag; the queries ConfigMap names every ADR-037 metric), `docs/07-operations.md` §7.

- [ ] Exporter Deployment (P5-D8): `postgres_exporter` by digest, `DATA_SOURCE_NAME` from the secret, `--disable-default-metrics`, `--extend.query-path`, port 9187, annotations `prometheus.io/scrape: "true"`, `prometheus.io/port: "9187"`, `prometheus.io/path: /metrics`; NetworkPolicy: egress to Postgres only, ingress on 9187 from `metrics.scrapeFrom` (namespace selector, default: same namespace).
- [ ] Alert rules (both the `PrometheusRule` and the plain ConfigMap carry the same YAML): `EnergyPlatformTargetLate` (`energy_platform_freshness_status{status="late"} == 1` for 2 cadences), `EnergyPlatformPipelineFailed` (`energy_platform_pipeline_failed == 1`), `EnergyPlatformSourceUnavailable` (warning; `for: 1h`), `EnergyPlatformNoFreshnessRow` (exporter up but no row for a committed target for 30 min), `EnergyPlatformRestoreDrillFailed` (`kube_job_status_failed{job_name=~"restore-drill.*"} > 0`, documented as needing kube-state-metrics).
- [ ] Dashboard JSON: freshness age per target, status timeline, runs by state, drill outcomes.
- [ ] Local: port-forward the exporter and assert `energy_platform_freshness_age_seconds{target="ote_intraday_market"}` present (this is the `make smoke-test` freshness check).
- [ ] Commit `feat(observability): freshness exporter, alert rules, PodMonitor/PrometheusRule behind the operator flag, Grafana dashboard (ADR-037 / ADR-012, D-6)`.

### Task 5.13 — `make smoke-test`, docs, roadmap, progress

**Files:** `Makefile` (`smoke-test`), `docs/07-operations.md` (index, RPO/RTO table with measured values), `docs/05-constraint-matrix.md` (§2 gate rows final), `docs/03-roadmap.md` (Phase 5 checkboxes; V-11 stays open; demo deploy box ticked only if the author ran it), `docs/progress.md` (dated entry + Phase 6 starter prompt), `README.md` (reproduce block: `make local-up && make smoke-test`).

- [ ] `make smoke-test` = `helm test energy-platform -n energy-platform --logs` (re-runs the smoke hook) → exporter port-forward and the freshness metric assertion → `kubectl create job --from=cronjob/restore-drill restore-drill-dry-run` with `--dry-run` injected via `RESTORE_DRILL_ARGS` env → wait and print the log; every step fails loudly.
- [ ] Clean-clone proof: `git clone . /tmp/clean && cd /tmp/clean && make local-down local-up smoke-test` (kind cluster name shared; the Make targets are idempotent) — record the wall clock.
- [ ] Docs, roadmap ticks, progress entry, Phase 6 starter (verbatim from `03`). `make check` green.
- [ ] Commit `docs(phase-5): operations runbook, gate rows, roadmap ticks, progress entry with the Phase 6 starter`.

## Author tasks (Level 3, never the agent)

1. Budget alerts: Hetzner €25/month, OCI €10/month (consoles), then `make terraform-plan-hcloud` review and `terraform apply` from the plan file.
2. Create the GitHub remote for this repository, push `main`, set repository variables `DEMO_CLUSTER_URL` and `DEMO_CLUSTER_CA` from the Terraform outputs, create the namespace `Secret` from the outputs (`make print-demo-secret-template` prints the shape), run `deploy-demo` once by hand, then enable `push: main`.
3. V-11 one-off probe on the reference cluster (optional; informs the tenant README claim).
4. Delete the 2026-09-22 scratch buckets after their locks expire (never the agent).

## Acceptance for the phase

`make check` green on `main`; `make helm-lint` and `make terraform-validate` real and green; from a clean clone `make local-up && make smoke-test` passes (hooks ran migrations and the smoke, egress assertions printed, freshness metric present, restore drill dry-run ok); one real restore drill and the rollback drill passed on kind with transcripts in `docs/07-operations.md`; `hcloud` plan produced and summarised; tenant/demo values render; the deploy workflow exists and is blocked only on the author tasks above; ADR-035, ADR-036, ADR-037 accepted; roadmap Phase 5 boxes ticked except those that depend on author tasks, which say so.
