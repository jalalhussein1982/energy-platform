# 02 — Architecture Decisions (Step 2)

| | |
|---|---|
| Status | Locked items are **FROZEN** as of 2026-09-19. Open items are tracked in §4 and are resolved only by appending a dated ADR, never by silently coding around them. **Reconciled 2026-09-19** with `00-assumptions.md` §5/§6: ADR-001 amended, ADR-003 revised, ADR-016 added, B-1…B-6 resolved (see `docs/adr/`). Superseded text is kept under a dated note, never deleted. |
| Predecessor | `docs/00-assumptions.md` (assumptions register, verification log), `docs/01-data-scope.md` (Step 1 — sources, tiers, modality matrix) |
| Successor | `docs/03-roadmap.md` (execution plan) |
| Audience | Humans and coding agents. If you are an agent: this document constrains you. Do not "improve" a locked decision inside a task PR; open a decision PR instead. |

---

## 0. Reading guide

- **Locked** = decided. Rationale is recorded so it can be challenged later, but a task does not reopen it.
- **Locked in principle, unwritten** = the direction is fixed; the detailed ADR still has to be authored (ADR-011, ADR-012, ADR-013).
- **Open** = undecided. Each open item lists options and a default. The default is what you implement if nobody objects; it is not a decision until an ADR records it.

---

## 1. Framing

### 1.1 Reading of the assignment

- "Intraday energy data" is read as **data published at intraday cadence** about the Czech/CE power system, with **intraday market results as the core subset** (see `01-data-scope.md`).
- The deliverable under evaluation is the **engineering harness** — how coding agents and junior engineers are led and constrained — not the scrapers themselves. Scrapers are the exhaust; the harness is the engine.
- The target list is a **modality matrix** (HTML table, dated file download, SOAP/XML, keyed REST/JSON, rate-limited REST/XML). It functions as a test suite for the framework.

### 1.2 Role of LLMs (authority by proximity to production)

| Proximity | Role | Authority |
|---|---|---|
| Build time | Author of platform code under supervision | Maximum, gated by review and CI |
| Design time | Contributor of new targets via the golden path | Contractual (manifest + parser + fixtures + tests only) |
| Maintenance time | Drift triage proposing patches as PRs | Advisory, read-only on production |
| Run time | — | **None.** No LLM in the hot path. |

### 1.3 Regulatory assumption (stated, not overstated)

> The architecture assumes operation within an environment subject to Czech critical-infrastructure/cybersecurity requirements. Czech law explicitly regulates major electricity generation, distribution and trading services and imposes supplier-risk controls.

Basis: Act No. 264/2025 Coll. on Cybersecurity (published 4 Aug 2025, effective 1 Nov 2025, replacing Act No. 181/2014 Coll.) and its implementing decrees — 408/2025 (regulated services), 409/2025 (security measures, higher-obligations regime), 410/2025 (lower-obligations regime).

Constraints:
- Do **not** write "ČEZ is regulated because it is a nuclear operator" or name specific ČEZ legal entities as regulated without verification.
- The scope claim about Decree 408/2025 must be checked against the decree's primary text before it appears in any submitted document (open item V-2).
- Consequence for design: anything ČEZ could not reproduce, audit, or move is disqualifying. Sovereignty is expressed as **portability plus a documented residency policy**, never as a vendor binding.

---

## 2. Locked decisions

### ADR-000 — One platform library, many clients

**Decision.** All capability lives in one Python library (`energy_platform`). The CLI (`energyctl`), the MCP server, the scaffolding templates and the CI gates are thin clients of that library. There is no agent-only path and no human-only path.

**Rationale.** A junior engineer and a coding agent must be two clients of the same constrained interface. Two parallel paths guarantee drift and double the attack surface.

**Consequences.** Any feature that exists only in the MCP server or only in the CLI is a bug. Governs every ADR below.

---

### ADR-001 — Deployment abstraction *(amended 2026-09-19 by `docs/adr/ADR-001-amend-three-profiles.md`)*

**Decision.** Kubernetes is the application deployment contract. Helm defines workloads. Terraform provisions infrastructure only. **Three** reproducibility profiles; platform code is identical across them, only Helm values and Terraform differ:

| Profile | Where | Cluster-level capability | Postgres | Secrets | Metrics |
|---|---|---|---|---|---|
| `local` | kind on a laptop | We install everything (ingress-nginx, cert-manager, MinIO×2) | `statefulset` | SOPS-decrypted `Secret` | `/metrics` + annotations |
| `tenant` | Any shared cluster (reference: e-INFRA Rancher; scenario A of `00` §1) | **None** — consume by name (`ingressClassName`, `clusterIssuer`, `storageClassName`) | `statefulset` or `external` (`cnpg` only where the operator pre-exists) | plain `Secret` from CI/SOPS | `/metrics` + annotations (`PodMonitor` behind flag where prometheus-operator pre-exists) |
| `own-cluster` | Terraform on OpenStack (reference: MetaCentrum Cloud; scenario B/C) | Operators allowed behind values flags | `cnpg` | ESO behind `secrets.eso.enabled` | `PodMonitor` behind `metrics.operator.enabled` |

```text
deployment/
├── local/            # kind + Helm, driven by Make. No Terraform.
├── tenant/           # values only (values-tenant.yaml, values-<env>.yaml). No Terraform.
├── own-cluster/      # Terraform provisions (network/, nodes/, storage/); Helm deploys.
│   ├── terraform/
│   └── values-own-cluster.yaml
└── helm/
    └── energy-platform/
```

- `make local-up` = `kind create cluster` → Helm dependencies → Helm platform → migrations → smoke tests.
- `tenant`: `helm upgrade --install` with tenant values into a namespace that forbids CRDs; every pod is `restricted`-PSS-clean with requests/limits (`00` A-8, A-14). This is the first real environment (03 Phase 5).
- `terraform apply` (own-cluster profile) = networking → Kubernetes nodes/cluster → storage → security groups; then Helm.
- CI runs `terraform validate` and `terraform test` with mock providers so the own-cluster profile is proven without credentials; CI also renders the chart with tenant values and lints it against the restricted Pod Security profile.
- **Anything cluster-level appears only in `own-cluster`, behind a flag, never in the core chart.**

**Reference environment.** MetaCentrum / e-INFRA CZ is the **assumption base** from which the constraints above were derived and verified (`00` §2, §5). It is *not* the production platform and is never named as such (academic-only terms, best-effort SLA, not reproducible by the evaluator).

**Rejected.** Terraform-managed kind cluster (an obscure provider used only to claim "everything is Terraform"). Two profiles with `openstack` doing double duty (hides the tenant case). A separate chart per profile (three drifts). Naming MetaCentrum/e-INFRA as the production platform.

**LLM inference.** Any local/on-prem model is reached through the OpenAI-compatible backend of ADR-009. No GPU is on the platform's critical path.

> **Superseded by ADR-001-amend on 2026-09-19** — original two-profile text kept for the record:
>
> **Decision (original).** Kubernetes is the application deployment contract. Helm defines workloads. Terraform provisions infrastructure only. Two reproducibility profiles:
>
> ```text
> deployment/
> ├── local/            # kind + Helm, driven by Make. No Terraform.
> │   ├── kind-config.yaml
> │   └── values-local.yaml
> ├── openstack/        # Terraform provisions; Helm deploys.
> │   ├── terraform/
> │   └── values-openstack.yaml
> └── helm/
>     └── energy-platform/
> ```
>
> - `make local-up` = `kind create cluster` → Helm dependencies → Helm platform → migrations → smoke tests.
> - `terraform apply` (openstack profile) = networking → Kubernetes nodes/cluster → storage → security groups; then Helm.
> - CI runs `terraform validate` and `terraform test` with mock providers so the OpenStack profile is proven without credentials.
>
> **Rejected.** Terraform-managed kind cluster (an obscure provider used only to claim "everything is Terraform"). Naming MetaCentrum/e-INFRA as the production platform (academic-only terms, best-effort SLA, not reproducible by the evaluator). MetaCentrum may be mentioned only as one environment against which the generic OpenStack profile was tested.
>
> **LLM inference.** Any local/on-prem model is reached through the OpenAI-compatible backend of ADR-009. No GPU is on the platform's critical path.

---

### ADR-002 — Storage and recovery model

**Decision.** Three tiers with different protection semantics.

| Tier | Content | Authority | Protection |
|---|---|---|---|
| **Bronze** | Immutable source captures | Irreplaceable | Versioned + object-locked object store; **independent copy in a second failure domain**; lifecycle to cold tier |
| **Silver** | Canonical normalised observations | **PostgreSQL is authoritative** | pgBackRest/WAL-G with PITR; reconstructable from Bronze |
| **Gold** | Serving aggregates and exports (incl. Parquet) | Disposable | Rebuild only |

Bronze layout:

```text
bronze/
  blobs/<sha256[:2]>/<sha256>            # content-addressed bytes, written once
  captures/<target_id>/<YYYY>/<MM>/<DD>/<fetch_ts>.json   # capture log entry
```

Capture log entry (metadata) — **no `parser_version` here**; parser lineage belongs to Silver:

```json
{
  "target_id": "ote_intraday_market",
  "fetch_time": "2026-09-19T10:05:03Z",
  "source_url": "...",
  "http_status": 200,
  "content_type": "...",
  "sha256": "...",
  "content_changed": false,
  "source_timestamp": null
}
```

Blob store and capture log are separate: an unchanged page produces a new capture entry (`content_changed: false`) and no new blob. The unchanged signal feeds staleness detection (ADR-012) and drift baselines.

**Backup semantics.**

| Asset | Protection |
|---|---|
| Bronze | immutable/versioned + independent replication |
| PostgreSQL | WAL-G/pgBackRest + PITR |
| Gold / Parquet | rebuild from Silver |
| Git / configuration | Git remote |
| Secrets | external secret management; never in backups in plaintext |

**RPO / RTO design targets** (targets for this repository, not claims about production ČEZ requirements):

| | RPO | RTO |
|---|---|---|
| Bronze captures | ≤ source polling interval | < 1 h |
| Silver (Postgres) | ≤ 15 min | < 1 h |
| Gold | none (rebuild) | rebuild time |
| Full rebuild from Bronze | — | documented and benchmarked |

**Restore drill.** A scheduled CI job restores Bronze and Postgres into a scratch environment and asserts row counts and checksums. A backup that has never been restored is a hypothesis.

**Rejected.** Parquet and Postgres as dual authoritative Silver (dual-write inconsistency). A single-failure-domain object store described as "backup".

*(2026-09-19, `00` §5 V-6: versioning and object lock verified on the reference S3 store; the second independent endpoint is Swift on a different site. The cold-tier storage class could not be demonstrated, so "lifecycle to cold tier" is a profile value — `bronze.coldStorageClass`, empty = no transition — never a hard requirement. Bronze replication is an `rclone` job, not native bucket replication.)*

---

### ADR-003 — Orchestration *(revised 2026-09-19 by `docs/adr/ADR-003-rev-orchestration-without-crds.md`)*

**Decision.** Kubernetes **`CronJob`** (core API) as the trigger plus a **Postgres run ledger** owned by the platform. **One** CronJob template in the Helm chart, rendered once per target from `targets/*/manifest.yaml`. Targets cannot define their own topology.

Run shape — **two steps**, not six:

```text
CronJob(target_id, capture)  : fetch → persist raw → ack → ledger row (state=captured)
CronJob(target_id, process)  : claim unprocessed captures from ledger → parse → validate → normalise → upsert → quality checks
CronJob(gap-detector)        : expected intervals (cadence calendar) vs ledger + Silver → enqueue replays into ledger
```

The run ledger (`runs`: `target_id`, `scheduled_for`, `lease_owner`, `lease_until`, `state`, `image_digest`, `parser_version`, `bronze_ref`) supplies what `CronJob` lacks: idempotency (one run per `(target_id, scheduled_for)`), lease-based concurrency control across pods, missed-run detection, and the gap detector's input. **The ledger is not optional**; `CronJob` alone has weak missed-run semantics (`startingDeadlineSeconds`) and no cross-target concurrency control.

The only boundary that buys availability is between capture and process. Finer decomposition multiplies pod launches (≈17k/day for 30 targets at 15-min cadence) for no resilience gain.

**Gap detector.** No Kubernetes primitive has partition/backfill semantics. The reconciliation loop compares expected intervals per target against the ledger and observed Silver rows and enqueues replays. This is the capability Dagster provides natively; choosing CronJob+ledger is choosing fewer concepts over free backfills.

**Rejected.** Argo Workflows (cluster-scoped CRDs; a namespace tenant cannot install them, and on the reference cluster cannot even create `CronWorkflow`s where they are installed — `00` §5 V-4). Kubernetes CronJob *alone* (no run semantics — hence the ledger). Airflow and Kafka (volume does not justify them). Temporal (excellent, disproportionate). Dagster (defensible; rejected for the second control plane). Keeping Argo as an optional profile (two schedulers = entropy).

> **Superseded by ADR-003-rev on 2026-09-19** — original text kept for the record:
>
> **Decision (original).** Argo Workflows / CronWorkflows on Kubernetes. **One** workflow template, parameterised by `target_id`. Targets cannot define their own topology.
>
> Run shape — **two pods**, not six:
>
> ```text
> CronWorkflow(target_id)
>    │
>    ├── capture   : fetch → persist raw → ack           (in-process)
>    │
>    └── process   : parse → validate → normalise → upsert → quality checks   (in-process)
> ```
>
> The only boundary that buys availability is between capture and process. Finer decomposition multiplies pod launches (≈17k/day for 30 targets at 15-min cadence) for no resilience gain.
>
> **Gap detector.** Argo has no partition/backfill semantics. A reconciliation loop compares expected intervals per target (from its cadence calendar) against observed Silver rows and enqueues replays. This is the capability Dagster provides natively; choosing Argo is choosing fewer concepts over free backfills, and the ADR file must say so.
>
> **Rejected.** Kubernetes CronJob alone (no workflow semantics, no visibility). Airflow and Kafka (volume does not justify them). Temporal (excellent, disproportionate). Dagster (defensible; rejected for the second control plane and to keep one K8s-native concept set).

---

### ADR-004 — Runtime availability model

**Decision.** Availability is defined at the application level by these invariants:

```text
Failure of one scraper worker     ≠  loss of scheduled ingestion
Failure of one processing pod     ≠  loss of source payload
Duplicate execution               ≠  duplicate canonical records
Parser failure                    ≠  loss of raw capture
Database outage                   ≠  loss of source observations
Source outage                     ≠  platform incident (see ADR-012)
```

Ordering is therefore fixed:

```text
FETCH → WRITE RAW → ACKNOWLEDGE CAPTURE → PROCESS
```

Execution is at-least-once; correctness comes from an idempotent upsert keyed on the canonical schema (ADR-011, ADR-018) and from the **run ledger** (ADR-003 rev.): one row per `(target_id, scheduled_for)`, lease-based claims, `image_digest`/`parser_version` lineage. Replay is a ledger operation: it enqueues runs for existing Bronze captures and never refetches. The gap detector (ADR-003 rev.) writes those replay rows; `energyctl replay` does the same by hand:

```bash
energyctl replay --target ote_intraday --from 2026-09-19T10:00Z --to 2026-09-19T12:00Z
energyctl replay --target ote_intraday --from … --to … --parser-version <bad>   # repair after a bad release (ADR-016)
```

*(2026-09-19: replay and gap detector re-pointed at the run ledger; see ADR-003 rev. Original wording said only "replay never refetches".)*

---

### ADR-005 — Canonical extension contract

**Decision.** Adapters own **syntax**; the platform owns **semantics**.

- **Fetch** is declarative per modality (URL template, method, headers, auth reference, pagination; SOAP body is a template, still data). No target writes fetch code.
- **Parse** is the only code a target may contribute, and only when the platform's generic parser for that modality is insufficient.
- **Normalise** is a declarative field mapping in the manifest (source field → canonical field, unit, timezone, interval convention, sign convention), executed by the platform.

A target is exactly:

```text
targets/<target_id>/
├── manifest.yaml     # fetch spec, modality, mapping, cadence, license, terms_url, host allowlist
├── parser.py         # optional; implements the Parser protocol for this modality
├── fixtures/         # Bronze objects reused as test input
└── tests/            # golden-value contract tests
```

Anything that cannot be expressed this way is a platform gap, handled by a human-reviewed PR to `energy_platform/` — never by widening what a target may do.

**Rejected.** `fetch()` and `normalize()` on the adapter (moves timezone/unit/sign errors into code that juniors and agents write).

---

### ADR-006 — Agent authority model

| Level | Name | Scope |
|---|---|---|
| 0 | READ | docs, schemas, existing targets, fixtures, logs |
| 1 | GENERATE | target scaffold, parser, manifest, fixtures, tests, documentation |
| 2 | PROPOSE | repository patch, workflow configuration, PR |
| 3 | FORBIDDEN | merge to `main`, production secrets, `terraform apply` (production), `kubectl` write (production), production database mutation, archive deletion |

**Dependency changes are their own gate**, not a Level-2 proposal: hash-pinned lockfile, dependency allowlist checked in CI, ADR required for a new package. An agent may open the PR; CI fails it until a human extends the allowlist. Rationale: dependency hallucination/slopsquatting is in the threat model (ADR-008).

Enforcement is mechanical: branch protection, CODEOWNERS on `energy_platform/` and `deployment/`, deploy identities (OIDC) that no agent holds.

---

### ADR-007 — MCP

**Decision.** An MCP server exposes the golden path as tools (`read_repository`, `inspect_target`, `scaffold_target`, `write_target_file`, `validate_target`, `record_fixture`, `run_target_tests`, `open_pr`) and wraps the same library as the CLI (ADR-000).

Two modes:

- **Developer mode** — CLI plus ordinary filesystem. MCP is the *preferred route*; **CI is the enforcement**.
- **Constrained-agent mode** — the agent runs in a sandbox with no shell, no `kubectl`, no `terraform`, no secrets, no `main`; repository mutation happens only through the allowed tools. Only here is MCP part of the authority boundary. The sandbox (container, egress limited to the MCP server and the Git remote) is the boundary; client permission settings are policy, not boundary.

Optional Role C (consumer-facing query MCP over Silver/Gold) is product, not harness — open item D-9.

---

### ADR-008 — Prompt-injection and supply-chain threat model

**Decision.** `docs/threat-model.md` is a first-class deliverable. The drift-triage agent reads hostile third-party content by definition.

Mandatory flow:

```text
Internet content → UNTRUSTED DATA → bounded extractor/sample → LLM triage → suggested patch → CI → human
```

Never: `Internet → LLM → production action`.

Minimum threat catalogue: indirect prompt injection; malicious source response; dependency hallucination/slopsquatting; credential exfiltration; unsafe shell generation; SSRF via manifest URL; malicious redirects; archive poisoning; PR supply-chain attack; mapping-level data poisoning (a patch that silently flips a sign or unit).

Mechanisms locked:
- **SSRF**: manifest URLs validated against a per-target host allowlist in the schema **and** Kubernetes egress `NetworkPolicy` so a capture pod can reach only its declared hosts.
- **Data poisoning**: contract tests assert **golden values**, not merely "parses without error".
- **Licensing**: `license` and `terms_url` are mandatory manifest fields; the scheduler refuses targets without them (this is also how EPEX/Nord Pool stays out).
- Triage agent: least-privilege tools, content passed as data with length limits, output restricted to a PR.

---

### ADR-009 — LLM backend

**Decision.** `LLMBackend` Protocol with one implementation: OpenAI-compatible HTTP.

```yaml
llm:
  provider: openai-compatible
  base_url: ${LLM_BASE_URL}
  model: ${LLM_MODEL}
```

Works unchanged against vLLM, Ollama, e-INFRA inference, or a corporate endpoint. **Hard requirement:** LLM unavailable → data platform operates normally. No GPU on the critical path.

---

### ADR-010 — Local reproduction

**Decision.** The acceptance criterion is literal:

```bash
git clone <repository>
cd energy-platform
make local-up
make smoke-test
make demo
```

with **no cloud credentials and no LLM credentials**. `make demo` runs the full path (target → capture → Bronze → parse → canonical records → PostgreSQL → query) **on fixtures by default**; live fetch is opt-in. CI tests never require network.

---

### ADR-011 — Canonical schema *(locked in principle, unwritten)*

Direction fixed:
- `EnergyObservation` is **bitemporal**: delivery interval (valid time) and publication/observation time (transaction time), plus source version.
- Must survive DST days with 92 and 100 quarter-hour intervals; this is a mandatory property test.
- Interval-start vs interval-end and import/export sign conventions are explicit fields of the mapping, never implicit.
- The upsert key of ADR-004 is defined here.
- Written together with ADR-013 in `docs/04-contracts.md` (they are two sides of one contract).

---

### ADR-012 — Availability as freshness *(locked in principle, unwritten)*

Direction fixed:
- SLI = age of the newest observation per target relative to its expected cadence.
- SLO per tier; alerts fire on **staleness**, not pod restarts.
- Metrics distinguish `source_unavailable` from `pipeline_failed`. A ČEPS outage at 03:00 is not our incident.

---

### ADR-013 — Manifest schema *(locked in principle, unwritten)*

Direction fixed: declarative, versioned JSON Schema, one file per target, mandatory `license`/`terms_url`/`allowed_hosts`, modality-specific fetch block, mapping block executed by the platform. Written with ADR-011. Parameters fixed by ADR-017.

---

### ADR-016 — Release and rollback model *(added 2026-09-19; full text in `docs/adr/ADR-016-release-and-rollback.md`)*

**Decision.**
1. A release is an immutable bundle: chart version + image **digest** + target manifests. Rollback = `helm rollback`. CI refuses mutable tags.
2. `helm upgrade --atomic --wait` plus a **`helm test` hook** running one fixture capture+process against the new image; the freshness SLI over the next two cadences confirms.
3. Migrations are **expand/contract**, compatible with code N−1, run as a `pre-upgrade` hook, each with a **downgrade script exercised in CI**; the application refuses to start on an incompatible schema.
4. Data from a bad release is repaired by `energyctl replay --parser-version <bad>` from Bronze, using ledger lineage — never by rollback.
5. Semantic failures are caught upstream: golden tests, quality checks, optional canary target group (D-13).
6. Rollback is **drilled** on a schedule, like restore.

**Rejected.** Argo Rollouts / Flagger (CRDs); `kubectl rollout undo` alone.

---

### ADR index (files in `docs/adr/`, 2026-09-19)

| ADR | Resolves | Status |
|---|---|---|
| ADR-001-amend-three-profiles | amends ADR-001 | ACCEPTED |
| ADR-003-rev-orchestration-without-crds | supersedes ADR-003 | ACCEPTED |
| ADR-014-tooling-baseline | B-4 | ACCEPTED |
| ADR-015-ci-platform | B-5 (+ A-13) | ACCEPTED |
| ADR-016-release-and-rollback | new | ACCEPTED |
| ADR-017-manifest-format-and-registration | B-1 | ACCEPTED |
| ADR-018-canonical-schema-details | B-2 | ACCEPTED |
| ADR-019-generic-parsers-and-allowlist | B-3 | ACCEPTED |
| ADR-020-test-strategy | B-6 | ACCEPTED |

---

## 3. Sequence

1. **Source domain** — complete enough to begin (`01-data-scope.md`). ✔
2. **Architecture ADRs** — this document. ✔ (011/012/013 pending authoring)
3. **Engineering harness** — repository contract, library, CLI/MCP, CI gates, `CLAUDE.md`/`AGENTS.md`.
4. **Source discovery/verification of Tier-1 targets, performed through the harness.**
5. **Platform + IaC + HA + DR implementation.**
6. **Blind acceptance test** — fresh agent and junior human.

Harness before code. Step 4 is the harness's own first test.

---

## 4. Open decisions

### 4.1 Blocking Step 3 — **all resolved 2026-09-19** (defaults adopted unless noted)

| ID | Item | Options | Default | Resolved by |
|---|---|---|---|---|
| B-1 | Manifest format and registration | YAML vs TOML; JSON Schema versioning; parser registration via entry points vs directory convention; secret references | YAML; versioned JSON Schema; directory convention; `secretRef` | ADR-017 |
| B-2 | Canonical schema details (ADR-011) | interval as `tstzrange` vs start+duration; revisions as version column vs history table; `observed_at` = fetch time vs source publication time | `tstzrange`; append-only versions with a current view; store both timestamps | ADR-018 (no `observed_at` column; `source_published_at` + `fetched_at` + `processed_at` per 01 §6.1) |
| B-3 | Generic parsers in v1 and dependency allowlist | html-table, xlsx, xml/soap, json-path, csv; library choices | all five; `lxml`, `openpyxl`, `pydantic` v2 | ADR-019 |
| B-4 | Tooling baseline | Python version; `uv`; `ruff`; `mypy --strict`; `import-linter`; `pre-commit`; CODEOWNERS | all; Python 3.12 | ADR-014 |
| B-5 | CI platform | GitHub Actions vs GitLab CI | GitHub Actions unless ČEZ indicates GitLab (ask) | ADR-015 — cannot ask; GitHub Actions assumed (`00` A-13); workflows are thin wrappers over Make |
| B-6 | Test strategy | fixtures as reused Bronze objects vs VCR cassettes; golden file format; property tests for DST; nightly-only live smoke | Bronze objects as fixtures; YAML goldens; Hypothesis for DST; nightly live smoke | ADR-020 |

### 4.2 Deferrable to Steps 4–5

| ID | Item | Options | Default |
|---|---|---|---|
| D-1 | Kubernetes bootstrap on OpenStack | Magnum vs Terraform VMs + cloud-init k3s/RKE2 | VMs + cloud-init k3s/RKE2 (Magnum not universal) |
| D-2 | Postgres as a **DSN contract** (changed 2026-09-19, `00` §6; was "engine and HA") | chart takes a DSN; profiles provide Postgres via `postgres.mode` = `statefulset` \| `cnpg` \| `external`; engine (plain vs TimescaleDB) still open | `statefulset` for local/tenant, `cnpg` for own-cluster (and for tenant where the operator pre-exists, `00` V-10), `external` for managed; engine decided by ADR before the Phase 2 schema |
| D-3 | Object storage per profile | MinIO local; Ceph RGW / Swift on OpenStack; what is the "independent copy" in each profile | MinIO (2 instances local); RGW + second bucket/region on OpenStack |
| D-4 | Gap detector internals | expected-interval calendars per target; tolerance windows; where it runs | CronWorkflow every cadence; tolerance = 2× cadence |
| D-5 | Polling cadence and politeness | per-target intervals; jitter; backoff caps; conditional requests (ETag/If-Modified-Since) | 5 min OTE IM; jitter ±10%; capped exponential backoff; conditional where supported |
| D-6 | Observability stack (changed 2026-09-19, `00` §6) | metrics exposure: `/metrics` + annotations vs `PodMonitor`; stack in local profile | **annotations by default; `PodMonitor` behind `metrics.operator.enabled`** (core chart needs no CRD); full stack only in `own-cluster`, minimal in local |
| D-7 | Secrets backend (changed 2026-09-19, `00` §6) | plain `Secret` vs External Secrets Operator; SOPS locally | **plain `Secret` by default (from CI/SOPS); ESO behind `secrets.eso.enabled`** (ESO absent on the reference cluster, `00` V-4); SOPS for local |
| D-8 | Retention and cold tier per profile | none local; lifecycle rules on OpenStack | Bronze hot 90 d → cold; Silver indefinite |
| D-9 | Serving layer and consumer MCP (Role C) | SQL only vs read API; MCP in/out | read-only FastAPI + SQL; MCP out unless time permits |
| D-10 | Drift-triage agent (Role B) | fully implemented vs pipeline with LLM step stubbed | pipeline built, LLM step stubbed, documented |
| D-11 | Gas intraday in v1 | in / out | in (one extra target, proves generality) |
| D-12 | Naming | `energyctl`, repository name | `energyctl`; repo `energy-platform` |
| D-13 | Canary target group (optional; added 2026-09-19 by ADR-016) | none vs one low-risk target on `image.canary` one cadence ahead of `image.stable` | out of v1; values keys reserved |

### 4.3 Verification (not design)

| ID | Item |
|---|---|
| V-1 | ČEPS public API mechanics; whether OTE public SOAP services still serve after the 2023 pruning; ENTSO-E token acquisition — outputs of Step 4 |
| V-2 | Decree 408/2025 scope and thresholds, from the primary text |
| V-3 | OTE and ENTSO-E terms of use on redistribution — bounds D-9 (whether Silver may be served outside the organisation) |
| V-4 | Tenant rights, CRDs, pre-installed operators, cluster services, quotas → `00-assumptions.md` §4/§5 (2026-09-19: CONFIRMED) |
| V-5 | OpenStack services, Magnum, quotas → `00` §5 (CONFIRMED: no Magnum) |
| V-6 | S3 endpoints, versioning, object lock, lifecycle, second endpoint → `00` §5 (PARTIAL: cold storage class unresolved) |
| V-7 | OpenAI-compatible inference endpoint → `00` §5 (CONFIRMED) |
| V-8 | Kube access identity and token lifetime → `00` §5 (PARTIAL: federated identity, but long-lived opaque Rancher token) |
| V-9 | Egress proxy and Tier-1 reachability from a pod → `00` §5 (CONFIRMED) |
| V-10 | Managed Postgres offering → `00` §5 (CONFIRMED: none) |

---

## 5. Final acceptance criteria

1. `git clone && make local-up && make smoke-test` passes on a clean machine with no credentials.
2. Restore drill passes from cold Bronze and Postgres backups.
3. Freshness dashboard shows per-target SLI; a simulated source outage produces `source_unavailable`, not `pipeline_failed`.
4. **Blind agent test**: a fresh agent, given only the README and the URL of an unseen source, opens a PR that passes CI and touches nothing outside `targets/<id>/`.
5. **Junior human test**: the same exercise via the CLI golden path, same outcome.
6. Negative harness tests: one deliberately bad PR per catalogued failure mode is rejected by the mapped gate.
