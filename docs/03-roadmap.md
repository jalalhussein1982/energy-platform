# 03 — Roadmap (execution plan for Claude Code)

| | |
|---|---|
| Status | Active. Checkboxes in this file are the single progress tracker; update them at the end of every session. |
| Inputs | `docs/00-assumptions.md`, `docs/01-data-scope.md`, `docs/02-architecture-decisions.md`, `docs/adr/` |
| Reconciled | 2026-09-19 with `00-assumptions.md` §6 (decisions session; no phase work done, no checkbox ticked) |
| Principle | **Harness before code.** No target is written until the harness that constrains target-writing exists. |

---

## 0. Session protocol (applies to every Claude Code session)

1. **Start**: read `CLAUDE.md`, `docs/00-assumptions.md` §2 (register) and §5 (verification log), `docs/02-architecture-decisions.md` §2 and §4, `docs/adr/`, and the current phase in this file. Nothing else until the plan exists.
2. **Plan first**: enter plan mode; write the plan to `docs/plans/phase-<N>.md` before touching code. Plan = ordered tasks, each with its acceptance check.
3. **One phase per session**, `/clear` between phases. If a phase needs two sessions, the second one starts by reading `docs/plans/phase-<N>.md` and the checkbox state below.
4. **Locked decisions are not reopened in a task.** If a task discovers a locked decision is wrong, stop, write `docs/adr/ADR-<NNN>-<slug>.md` as a proposal, and continue only after it is accepted.
5. **Open items are resolved by ADR, not by code.** Implementing the default from `02-architecture-decisions.md` §4 is allowed only after the ADR file recording it exists (a one-paragraph ADR is fine).
6. **Commit granularity**: one task, one commit, conventional-commit message. `make check` (lint + type + test) must be green before every commit.
7. **End**: tick checkboxes here, append a dated line to `docs/progress.md` (what was done, what was learned, what is next), commit.
8. **Never**: add a dependency without an ADR; write fetch or normalise code inside `targets/`; touch `deployment/` in a target PR; call live network from unit tests.

---

## 1. Phase map

| Phase | Name | Step in §3 of 02 | Sessions (est.) | Gate |
|---|---|---|---|---|
| 0 | Repository bootstrap | 3 | 1 | `make check` green on empty package |
| 1 | Contracts (ADR-011, ADR-013 → `docs/04-contracts.md`) | 3 | 1–2 | five example manifests validate; DST property tests pass |
| 2 | Platform core library | 3 | 3–4 | `make demo` runs on fixtures end-to-end into Postgres |
| 3 | Harness: CLI, MCP, CI gates | 3 | 2–3 | one bad PR per failure mode is rejected |
| 4 | Tier-1 source verification through the harness | 4 | 2–3 | all Tier-1 targets green on fixtures; nightly live smoke defined |
| 5 | Deployment, IaC, HA, DR, observability | 5 | 3–4 | clean-clone `make local-up && make smoke-test`; restore drill passes |
| 6 | Threat model, triage pipeline, documentation | 5 | 1–2 | `docs/threat-model.md` complete; triage pipeline runs with stubbed LLM |
| 7 | Blind acceptance tests | 6 | 1 | agent PR + junior dry-run pass without core changes |
| 8 | Submission packaging | — | 1 | README reproducible by a stranger |

---

## Phase 0 — Repository bootstrap

**Goal.** A repository that already enforces the constraints before any domain code exists.

**Deliverables.**
- [ ] `pyproject.toml` (Python 3.12, `uv`, hash-pinned lock), `ruff` (incl. banned-API rules: naive `datetime.now()`, `except: pass`, `requests` without timeout), `mypy --strict`, `import-linter` layers (`targets/` may import only `energy_platform.contracts`; `energy_platform/` never imports `targets/`).
- [ ] `Makefile`: `check`, `lint`, `type`, `test`, `local-up`, `local-down`, `smoke-test`, `demo`, `new-target`.
- [ ] `CLAUDE.md` and `AGENTS.md` (identical content, see Appendix B).
- [ ] `CODEOWNERS`, PR template (checklist mirrors the constraint matrix), branch protection notes.
- [ ] `docs/adr/` with `ADR-template.md`; `docs/plans/`; `docs/progress.md` *(these three already exist from the 2026-09-19 decisions session)*; `docs/threat-model.md` (stub with the ADR-008 catalogue as headings).
- [ ] `deps-allowlist.txt` and the CI check that fails on any lockfile package not in it.
- [ ] CI skeleton (GitHub Actions per ADR-015; workflow files are thin wrappers that only call Make targets): lint, type, test, allowlist, secret scan, `helm-lint` against the `restricted` Pod Security profile (A-14), `terraform validate`.
- [ ] Empty `energy_platform/` package with `contracts/` and `targets/` directories; a placeholder test so CI is green.
- [ ] `deps-allowlist.txt` seeded with the ADR-019 list; `ruff` banned-API rules include the egress rule (no `httpx`/`requests`/`urllib` import outside `energy_platform/fetch/`, A-7).

**Do not.** Write any parser, fetcher, or manifest. Do not choose Postgres/Timescale yet (D-2).

**Starter prompt.**
> Read CLAUDE.md, docs/00-assumptions.md, docs/02-architecture-decisions.md, docs/adr/ADR-014-tooling-baseline.md, docs/adr/ADR-015-ci-platform.md, docs/adr/ADR-019-generic-parsers-and-allowlist.md and docs/03-roadmap.md Phase 0. B-4 and B-5 are already resolved (ADR-014, ADR-015): implement them, do not rewrite them. Plan Phase 0 into docs/plans/phase-0.md, then execute it task by task. Stop after `make check` is green and update the roadmap checkboxes.

---

## Phase 1 — Contracts

**Goal.** The two sides of the one contract: what a source looks like (manifest) and what the destination looks like (canonical schema). Everything later is mapping between them.

**Deliverables.**
- [ ] ADRs resolving B-1, B-2, B-3, B-6 — *filed 2026-09-19 as ADR-017, ADR-018, ADR-019, ADR-020*; this phase implements them and may amend by a new ADR only.
- [ ] `docs/04-contracts.md` = ADR-011 (canonical schema) + ADR-013 (manifest schema), written together.
- [ ] `energy_platform/contracts/observation.py` — `EnergyObservation` (bitemporal: `delivery_interval` as `tstzrange`-equivalent, `published_at`, `observed_at`, `source_version`, `unit`, `sign_convention`), plus the upsert key definition.
- [ ] `energy_platform/contracts/manifest.py` — Pydantic model + exported JSON Schema (`schemas/manifest.v1.json`), mandatory `license`, `terms_url`, `allowed_hosts`, modality-specific `fetch` block, `mapping` block, `cadence`.
- [ ] `energy_platform/contracts/parser.py` — `Parser` protocol (input: Bronze capture; output: `Iterable[SourceRecord]`), nothing else.
- [ ] Five example manifests, one per modality (html-table, dated-file, soap-xml, rest-json-keyed, rest-xml-ratelimited), validating against the schema. Use real Tier-1 URLs from `01-data-scope.md`; they are not fetched in this phase.
- [ ] Property tests: DST spring (92 intervals) and autumn (100 intervals) days; interval-start vs interval-end mapping; sign inversion.

**Do not.** Write fetch or persistence code. Do not fetch from the network.

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md (§2 ADR-005, ADR-011, ADR-013; §4.1), docs/adr/ADR-017 … ADR-020, docs/01-data-scope.md, and docs/03-roadmap.md Phase 1. B-1, B-2, B-3, B-6 are resolved; implement them. Author docs/04-contracts.md and implement the contracts package with the property tests. Stop when the five example manifests validate and the DST tests pass.

---

## Phase 2 — Platform core library

**Goal.** The platform owns semantics end to end, runnable locally on fixtures.

**Deliverables.**
- [ ] `fetch/` — declarative fetchers per modality (httpx, timeouts, capped backoff with jitter, conditional requests, host-allowlist enforcement before any request).
- [ ] `bronze/` — blob store (SHA-256 keyed) + capture log; `content_changed` detection; S3 backend (MinIO locally) and an in-memory backend for tests; read path tries hot then cold and the capture log carries `tier` (ADR-021).
- [ ] `parse/` — generic parsers: html-table, xlsx, xml/soap, json-path, csv.
- [ ] `mapping/` — executes the manifest `mapping` block: units, timezone, interval convention, sign convention → `EnergyObservation`.
- [ ] `silver/` — Postgres schema and migrations (Alembic); bitemporal idempotent upsert per ADR-018; current-view. **Definition of done: every migration ships a downgrade script, exercised in CI (ADR-016 §3).**
- [ ] `ledger/` — the run ledger (ADR-003 rev.): `runs` table migrations (`target_id`, `scheduled_for`, `lease_owner`, `lease_until`, `state`, `image_digest`, `parser_version`, `bronze_ref`), lease claim/release, idempotent enqueue, missed-run query.
- [ ] `replay` and `gap_detector` modules (ADR-003 rev./ADR-004) operating on the ledger; `replay --parser-version` for ADR-016 repair.
- [ ] `energyctl` CLI: `validate`, `capture`, `process`, `replay`, `gaps`, `demo`.
- [ ] `make demo`: fixture → capture → Bronze → parse → map → Postgres → query, offline.
- [ ] ADR for D-2 (Postgres *engine*: plain vs TimescaleDB) written before the schema is created. The DSN contract and `postgres.mode` are already decided (02 §4.2 D-2, 2026-09-19).

**Do not.** Add a target under `targets/` yet — use the Phase 1 example manifests with recorded fixtures only. No Kubernetes.

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md, docs/adr/ADR-003-rev-orchestration-without-crds.md, docs/adr/ADR-016-release-and-rollback.md, docs/04-contracts.md and docs/03-roadmap.md Phase 2. Plan into docs/plans/phase-2.md. Implement the library in the order fetch → bronze → parse → mapping → silver → ledger → replay/gaps → CLI, committing per module with tests. Every migration has a downgrade script. `make demo` must run offline. Stop when it does.

---

## Phase 3 — Harness

**Goal.** Make the wrong thing impossible for both a junior and an agent. This is the deliverable the assignment is actually grading.

**Deliverables.**
- [ ] `docs/05-constraint-matrix.md`: table `failure mode → gate → test that proves the gate`. Minimum rows: hardcoded URL; naive datetime; swallowed exception; unbounded retry; positional parsing; duplicated utility; new dependency; PR touching outside `targets/<id>/`; missing fixture; missing golden; missing `license`; host not in allowlist; secret in code; fetch code inside a target; normalise code inside a target; **outbound HTTP outside `energy_platform.fetch`** (A-7); **workload without resource requests** (A-8); **mutable image tag** (ADR-016); **migration without downgrade** (ADR-016).
- [ ] `energyctl new-target <id> --modality <m>` scaffolder (manifest skeleton, fixture dir, golden test skeleton, README stub).
- [ ] `energyctl record-fixture <id>` (captures into `targets/<id>/fixtures/` as Bronze objects; opt-in network).
- [ ] MCP server (`energy_platform/mcp/`) exposing the ADR-007 tool set as thin wrappers over the library. Sandbox recipe (`deployment/sandbox/`): container with no shell tool access, egress limited to the Git remote.
- [ ] CI gates for every row of the constraint matrix; a target-PR path check (`targets/<id>/**` only).
- [ ] Contract-test harness auto-discovers every target and runs its goldens; a target without fixtures/goldens fails collection.
- [ ] Negative tests: `tests/harness/` contains one intentionally bad target per failure mode and asserts the correct gate rejects it.

**Do not.** Weaken a gate to make a negative test easier. Do not implement the drift-triage LLM step here.

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md (ADR-005 to ADR-008), docs/04-contracts.md and docs/03-roadmap.md Phase 3. Write docs/05-constraint-matrix.md first. Then implement scaffolder, MCP server and CI gates so that every matrix row has a mechanical gate and a negative test. Stop when all negative tests are rejected by their mapped gate.

---

## Phase 4 — Tier-1 source verification through the harness

**Goal.** The harness's first real workload. Agents "look around" at Level 1 authority only.

**Deliverables.**
- [ ] ADR for D-5 (cadence/politeness) and D-11 (gas in/out).
- [ ] Targets, each via `energyctl new-target` → `record-fixture` → goldens → PR: `ote_intraday_market`, `ote_ida`, `ote_dam`, `ote_imbalance_settlement`, `ceps_load`, `ceps_generation`, `ceps_imbalance`, `ceps_crossborder_flows`, `ceps_balancing_activated`, `entsoe_load_cz`, `entsoe_generation_per_type_cz`, `entsoe_physical_flows_cz`, (`ote_gas_intraday` if D-11 = in), `epex_intraday` as a `license: restricted` stub that the scheduler refuses.
- [ ] `docs/06-source-verification.md`: per source — endpoint verified, auth, rate limits observed, terms-of-use notes (V-1, V-3), quirks (decimal comma, DST rows, progressive fill).
- [ ] Nightly live-smoke workflow definition (not run in PR CI).

**Do not.** Edit `energy_platform/` in a target PR. If a source needs a platform change, open a separate PR with an ADR. Do not scrape anything without `license`/`terms_url` filled from the source's own terms page.

**Starter prompt.**
> Read CLAUDE.md, docs/01-data-scope.md, docs/04-contracts.md, docs/05-constraint-matrix.md and docs/03-roadmap.md Phase 4. For each Tier-1 target: scaffold with energyctl, verify the live endpoint once, record a fixture, write goldens with values you checked by hand against the fixture, and open a PR touching only targets/<id>/. Record findings in docs/06-source-verification.md. Stop when all listed targets pass contract tests offline.

---

## Phase 5 — Deployment, IaC, HA, DR, observability

**Goal.** Reproducible by the evaluator; resilient by the ADR-004 invariants; measurable by ADR-012.

**Deliverables.**
- [ ] ADRs for D-1, D-3, D-4 (D-6, D-7 are contracts in 02 §4.2; D-8 is resolved by ADR-021; an ADR is needed only for the `own-cluster` stack details).
- [ ] Helm chart `deployment/helm/energy-platform` (core = `tenant`-clean, no CRDs, `restricted`-PSS-clean, requests/limits on every workload): **`CronJob` template rendered once per target** from `targets/*/manifest.yaml` (capture, process), gap-detector `CronJob`, **run ledger** migrations as a `pre-upgrade` hook Job, Postgres per `postgres.mode` (`statefulset` \| `cnpg` \| `external`), MinIO ×2 (local), NetworkPolicies (egress per target allowlist), plain `Secret` by default with ESO behind `secrets.eso.enabled`, `/metrics` annotations with `PodMonitor` behind `metrics.operator.enabled`.
- [ ] **`helm test` hook** (ADR-016): one fixture capture+process end-to-end against the new image; `helm upgrade --atomic --wait` in every deploy Make target; images by digest only.
- [ ] **Rollback drill** (ADR-016 §6): scheduled job deploys revision N, then N+1 with an injected failure, asserts automatic rollback, zero Bronze loss, correct ledger state.
- [ ] `deployment/local/`: `make local-up` = kind → Helm deps → Helm platform → migrations → smoke tests.
- [ ] `deployment/tenant/`: values for a namespace-only deploy; **deploy to the reference cluster (e-INFRA Rancher, `00` §5 V-4) as the first real environment**; deploy identity per ADR-015 (namespace-scoped token in CI secrets, expiry recorded).
- [ ] `deployment/own-cluster/terraform/`: networking, nodes, cluster bootstrap (D-1 — Magnum is absent on the reference cloud, `00` §5 V-5), storage, security groups; sized to the verified quota (20 vCPU / 50 GB RAM / 1 floating IP); `terraform test` with mocks in CI.
- [ ] Backups: pgBackRest/WAL-G to object store; Bronze replication as an `rclone` job to the independent endpoint (S3 → Swift on the reference environment, `00` §5 V-6); **`bronze-tier` CronJob** per ADR-021 (`bronze.tiering.mode = none|move|lifecycle`) with the storage-class **probe in `helm test`** (a gateway that answers `400 InvalidArgument` or reports STANDARD fails the deploy); **restore drill** as a scheduled `CronJob` with assertions, including a replay that reads from the cold location.
- [ ] Observability: freshness SLI per target, `source_unavailable` vs `pipeline_failed`, alert rules, Grafana dashboard JSON.
- [ ] `make smoke-test`: cluster up, one capture+process run on a fixture target, freshness metric present, restore drill dry-run.

**Do not.** Put any LLM component in the Helm chart's critical path. Do not require credentials for the local profile.

**Starter prompt.**
> Read CLAUDE.md, docs/00-assumptions.md, docs/02-architecture-decisions.md (ADR-001 to ADR-004, ADR-012, ADR-016), docs/adr/, docs/03-roadmap.md Phase 5. Write the D-* ADRs first. Then build the Helm chart and local profile until `make local-up && make smoke-test` passes from a clean clone; then deploy the tenant profile to the reference cluster; then the own-cluster Terraform profile with `terraform test`; then backups, the restore drill and the rollback drill; then observability. Stop when all gates pass.

---

## Phase 6 — Threat model, triage pipeline, documentation

**Deliverables.**
- [ ] `docs/threat-model.md` complete: each ADR-008 catalogue item with mechanism, gate, residual risk.
- [ ] Drift-triage pipeline (D-10): contract-test failure → bounded extractor → `LLMBackend` (stubbed by default) → patch proposal → PR. Prompt-injection test cases in `tests/triage/` (hostile HTML fixtures must not alter the proposed patch beyond the manifest).
- [ ] `docs/07-adding-a-target.md`: the junior's page. Must be sufficient on its own for Phase 7.
- [ ] Architecture diagram (Mermaid in `docs/architecture.md`).

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md (ADR-007 to ADR-009), docs/05-constraint-matrix.md, docs/03-roadmap.md Phase 6. Complete the threat model, implement the triage pipeline with the LLM stubbed, write docs/07-adding-a-target.md as if for someone who has never seen this repository. Stop when the prompt-injection tests pass.

---

## Phase 7 — Blind acceptance tests

**Protocol.**
1. New Claude Code session, **`/clear`**, no prior context. Provide only: `README.md`, `docs/07-adding-a-target.md`, and the URL of an unseen Tier-3 source (e.g. an Open-Meteo endpoint).
2. Instruction: "Add this as a target and open a PR." Nothing else.
3. Record: files touched, CI result, whether `energy_platform/` was modified, number of turns.
4. Repeat via the CLI golden path following `docs/07-adding-a-target.md` literally, as a junior would (no MCP).
5. Write `docs/08-acceptance-report.md` with both runs. If either run required a core change or human architectural guidance, that is a Phase 3 defect: fix the harness, not the report.

- [ ] Agent run recorded
- [ ] Junior-path run recorded
- [ ] Defects fed back and closed

---

## Phase 8 — Submission packaging

- [ ] `README.md`: what it is, 5-line reproduce block (ADR-010), architecture diagram, how targets are added, how agents are constrained, what was deliberately not built and why (link to §4 defaults not implemented), and a section **"Assumptions and what they cost"** summarising `00-assumptions.md` §2 (reference environment, scenarios A/B/C, each assumption's cost if false, verification verdicts).
- [ ] `docs/ci-porting.md` stub: how to port the GitHub Actions wrappers to GitLab CI (ADR-015, A-13).
- [ ] `docs/` index; ADR log complete; progress log trimmed.
- [ ] Final clean-clone run on a machine that has never seen the repository.

---

## Appendix A — Bootstrap prompt (paste into Claude Code at the start of Phase 0)

```text
You are working in the energy-platform repository. Read, in order: CLAUDE.md,
docs/00-assumptions.md, docs/01-data-scope.md, docs/02-architecture-decisions.md,
docs/adr/ (all ACCEPTED), docs/progress.md, docs/03-roadmap.md.

Rules that override anything else you infer:
- Locked decisions in 02 §2 and ACCEPTED ADRs in docs/adr/ are frozen. Open items in
  02 §4 are resolved only by writing a one-paragraph ADR in docs/adr/ before
  implementing the default. B-1…B-6 are already resolved; do not rewrite them.
- The core chart is a tenant: no CRDs, restricted Pod Security, requests/limits on
  every workload. Orchestration is CronJob + run ledger (ADR-003 rev.), not Argo.
- Harness before code: no target under targets/ before Phase 3 is complete.
- Targets contribute manifest + optional parser + fixtures + golden tests, nothing else.
  Fetch and normalise are platform code.
- No new dependency without an ADR and an allowlist entry.
- Plan into docs/plans/phase-N.md before coding. One task, one commit, `make check` green.
- Update docs/03-roadmap.md checkboxes and docs/progress.md at the end of the session.

Begin Phase 0.
```

## Appendix B — `CLAUDE.md` skeleton (mirror to `AGENTS.md`)

```markdown
# energy-platform — agent instructions

## What this is
High-availability ingestion of public intraday energy data (OTE, ČEPS, ENTSO-E) with a
constrained extension path so a junior or an agent can add a target without touching core.

## Read first
docs/00-assumptions.md, docs/02-architecture-decisions.md (frozen), docs/adr/ (accepted), docs/04-contracts.md, docs/05-constraint-matrix.md.

## Layout
energy_platform/   core library — semantics live here (fetch, bronze, parse, mapping, silver)
targets/<id>/      manifest.yaml, optional parser.py, fixtures/, tests/  — syntax only
deployment/        helm/, local/, tenant/, own-cluster/terraform/, sandbox/
docs/              assumptions (00), decisions (02), contracts, roadmap, threat model, ADRs

## Commands
make check | make test | make demo | make local-up | make smoke-test
energyctl new-target <id> --modality <m> | energyctl record-fixture <id> | energyctl validate <id>

## Hard rules
- Never write fetch or normalise code in targets/. Use the manifest.
- Never add a dependency without docs/adr/ entry + deps-allowlist.txt.
- Never call the network from unit tests. Fixtures are Bronze objects.
- Never edit docs/01 or docs/02 inside a task; propose an ADR.
- A target PR touches only targets/<id>/. Anything else is a platform PR.
- Timezones: every datetime is aware; delivery intervals are tstzrange; DST days have 92/100 intervals.
- All outbound HTTP goes through energy_platform.fetch. Images by digest. Every migration has a downgrade.
- The core Helm chart needs no CRDs and passes the restricted Pod Security profile.
- Decimal comma is common in Czech sources; parse explicitly, never float() on raw strings.

## Authority
Level 0 read · Level 1 generate targets · Level 2 propose PRs · Level 3 forbidden:
merge to main, production secrets, terraform apply, kubectl write, prod DB mutation, archive deletion.
```
