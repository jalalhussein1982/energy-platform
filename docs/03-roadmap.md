# 03 — Roadmap (execution plan for Claude Code)

| | |
|---|---|
| Status | Active. Checkboxes in this file are the single progress tracker; update them at the end of every session. |
| Inputs | `docs/00-assumptions.md`, `docs/01-data-scope.md`, `docs/02-architecture-decisions.md`, `docs/adr/` |
| Reconciled | 2026-09-19 with `00-assumptions.md` §6 (decisions session); 2026-09-19 again with ADR-022…ADR-027 after the Codex pre-coding review (`docs/reviews/2026-09-19-codex-review-response.md`); 2026-09-19 Phase 5 and Phase 8 reworded per ADR-028 (demo environment, ACCEPTED) |
| Principle | **Harness before code.** No target is written until the harness that constrains target-writing exists. |

---

## 0. Session protocol (applies to every maintainer phase session)

A contributor session — adding a target or requesting an admission — follows
`docs/08-adding-a-target.md` instead and does none of the bookkeeping below (Phase 7 finding,
`docs/09-acceptance-report.md`).

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
| 0 | Repository bootstrap | 3 | 1 | `make check` green on empty package — **done 2026-09-19** |
| 1 | Contracts (ADR-011, ADR-013 → `docs/04-contracts.md`) | 3 | 1–2 | six example manifests validate; DST property tests pass — **done 2026-09-20** |
| 2 | Platform core library | 3 | 3–4 | `make demo` runs on fixtures end-to-end into Postgres — **done 2026-09-20** (S3 backend shipped the same day under ADR-032) |
| 3 | Harness: CLI, MCP, CI gates | 3 | 2–3 | one bad PR per failure mode is rejected — **done 2026-09-20** (54 rows, `make harness-check` + `pr-surface` in CI) |
| 4 | Committed-target verification through the harness (01 §3) | 4 | 1–2 | T1, T2, T3, E1 green on fixtures; nightly live smoke defined — **done 2026-09-20** (polling campaign closed without running, 2026-09-23) |
| 5 | Deployment, IaC, HA, DR, observability | 5 | 3–4 | clean-clone `make local-up && make smoke-test`; restore drill passes — **done 2026-09-22 (local), live demo 2026-09-23** (V-11 closed without running) |
| 6 | Threat model, triage pipeline, documentation | 5 | 1–2 | `docs/threat-model.md` complete; triage pipeline runs with stubbed LLM — **done 2026-09-23** |
| 7 | Blind acceptance tests | 6 | 1 | agent PR + junior dry-run pass without core changes — **done 2026-09-23** (3/3 pass, `docs/09-acceptance-report.md`) |
| 8 | Submission packaging | — | 1 | README reproducible by a stranger — **done 2026-09-23** (clean clone on a fresh VM: exit 0 in 199 s) |
| 9 | Gap closure | — | 1 | every gap closed or listed in the README with a reason; final clean clone — **done 2026-09-23**; the strictly blind re-run (G10) run and passed 2026-09-24 (`docs/09` run 4) |
| 10 | Correctness and recovery (review 2) | — | 3–4 | the eight P1 counterexamples of `codex-review/2026-09-24/` pass as negative tests on PostgreSQL; RPO stated per failure domain — **done 2026-09-24** (`docs/plans/phase-10.md`; 11 commits, 923 tests, 32 on PostgreSQL) |
| 11 | Grafana dashboards over Silver (private) | — | 1 | the two dashboards render on the demo through a port-forward, through the read-only role — **done 2026-09-24** (`docs/plans/phase-11.md`) |
| 12 | The local profile's object stores after MinIO | — | 1 | the clean-clone gate green again on RustFS chosen by probe — **done 2026-09-24** (`docs/plans/phase-12.md`) |
| 13 | Review 3 (codex-astra, 2026-09-25) | — | 1 | the four runtime probes no longer reproduce (negative tests on PostgreSQL), the alert path evaluates and delivers on kind, the availability boundary is stated, the final report matches the evidence — **done 2026-09-25** (`docs/plans/phase-13.md`) |

---

## Phase 0 — Repository bootstrap

**Goal.** A repository that already enforces the constraints before any domain code exists. **Done 2026-09-19** (`docs/plans/phase-0.md`, `docs/progress.md`).

**Deliverables.**
- [x] `pyproject.toml` (Python 3.12, `uv`, hash-pinned lock), `ruff` (incl. banned-API rules: naive `datetime.now()`, `except: pass`, `requests` without timeout), `mypy --strict`, `import-linter` layers (`targets/` may import only `energy_platform.contracts`; `energy_platform/` never imports `targets/`).
- [x] `Makefile`: `check`, `lint`, `type`, `test`, `local-up`, `local-down`, `smoke-test`, `demo`, `new-target`.
- [x] `CLAUDE.md` and `AGENTS.md` (identical content, see Appendix B).
- [x] `CODEOWNERS`, PR template (checklist mirrors the constraint matrix), branch protection notes.
- [x] `docs/adr/` with `ADR-template.md`; `docs/plans/`; `docs/progress.md` *(these three already exist from the 2026-09-19 decisions session)*; `docs/threat-model.md` (stub with the ADR-008 catalogue as headings).
- [x] `deps-allowlist.txt` and the CI check that fails on any lockfile package not in it.
- [x] CI skeleton (GitHub Actions per ADR-015; workflow files are thin wrappers that only call Make targets): lint, type, test, allowlist, secret scan, `helm-lint` against the `restricted` Pod Security profile (A-14), `terraform validate`.
- [x] Empty `energy_platform/` package with `contracts/` and `targets/` directories; a placeholder test so CI is green.
- [x] `deps-allowlist.txt` seeded with the **dev group as locked**; the runtime names approved by ADR-019 are listed as comments and become active entries in the phase that locks them. `ruff` banned-API rules include the egress rule; *(2026-09-19: extended by ADR-027 to standard-library egress/escape paths, plus a positive target surface check and a unit-test socket block; see `docs/plans/review-1.md`)*.

**Do not.** Write any parser, fetcher, or manifest. Do not choose Postgres/Timescale yet (D-2).

**Starter prompt.**
> Read CLAUDE.md, docs/00-assumptions.md, docs/02-architecture-decisions.md, docs/adr/ADR-014-tooling-baseline.md, docs/adr/ADR-015-ci-platform.md, docs/adr/ADR-019-generic-parsers-and-allowlist.md and docs/03-roadmap.md Phase 0. B-4 and B-5 are already resolved (ADR-014, ADR-015): implement them, do not rewrite them. Plan Phase 0 into docs/plans/phase-0.md, then execute it task by task. Stop after `make check` is green and update the roadmap checkboxes.

---

## Phase 1 — Contracts

**Goal.** The two sides of the one contract: what a source looks like (manifest) and what the destination looks like (canonical schema). Everything later is mapping between them. **Done 2026-09-20** (`docs/plans/phase-1.md`, `docs/04-contracts.md`, `docs/progress.md`).

**Deliverables.**
- [x] ADRs resolving B-1, B-2, B-3, B-6 — *filed 2026-09-19 as ADR-017, ADR-018, ADR-019, ADR-020*, amended the same day by ADR-022 (registries), ADR-023 (derivation identity), ADR-026 (host registry, `allow_insecure`), ADR-027 (decoded parser input, import allowlist); this phase implements them and may amend by a new ADR only.
- [x] `docs/04-contracts.md` = ADR-011 (canonical schema) + ADR-013 (manifest schema), written together.
- [x] `energy_platform/contracts/observation.py` — `EnergyObservation` (bitemporal: `delivery_interval` as `tstzrange`-equivalent; `source_published_at` (nullable), `fetched_at`, `processed_at`; `source_version`, `contract_version`, `derivation_id`; `unit`, `sign_convention`), plus the version identity / upsert key per ADR-023 *(2026-09-19: field names corrected to ADR-018/ADR-023; `published_at`/`observed_at` were wrong)*.
- [x] `energy_platform/contracts/registry.py` — dataset registry (`dataset_id`, identity key, metric set with unit/sign/null meaning, `contract_version`) seeded from `01` §6.3/§9 for T1, T2, T3, E1; `energy_platform/contracts/hosts.py` — host registry (host, allowed ports, `allow_insecure`) seeded with the `01` §3 hosts. Both under CODEOWNERS (ADR-022, ADR-026).
- [x] `energy_platform/contracts/manifest.py` — Pydantic model + exported JSON Schema (`schemas/manifest.v1.json`), mandatory `license`, `terms_url`, `allowed_hosts` (each ⊆ host registry), modality-specific `fetch` block, `contract` block (`dataset_id` ∈ registry, `metrics` ⊆ registered set, `decode`), `mapping` block, `cadence`, `history.max_age` (ADR-024), `allow_insecure` (ADR-026).
- [x] `energy_platform/contracts/parser.py` — `Parser` protocol (input: `DecodedDocument`, produced by the platform per `contract.decode`; output: `Iterable[SourceRecord]`), nothing else (ADR-027 §2).
- [x] **Six** example manifests validating against the schema: three real committed contracts from `01-data-scope.md` §3 (soap-xml = T1 `GetImPricePeriodE`; dated-file with HTML discovery step = T2; a second soap-xml = T3 ČEPS `Load`) and three **shape-only** (html-table; rest-json-keyed = a token-keyed JSON API via `secretRef`; rest-xml-ratelimited = ENTSO-E's shape, class B, optional — *2026-09-20: ENTSO-E serves XML, so it is the rest-xml example, plan P1-D5*). Every modality of the matrix appears at least once. Nothing is fetched in this phase. *(2026-09-19: count fixed after review F14 — "five" undercounted because T1 and T3 share a modality.)*
- [x] `docs/04-contracts.md` takes 01 §6–§9 as its source: envelope fields, `dataset_id` registry with identity keys, metric registry with units/sign/null meaning, revision and ordering rules. No field invented, none dropped.
- [x] Property tests: DST spring (92 intervals) and autumn (100 intervals) days; interval-start vs interval-end mapping; sign inversion; decimal-comma parsing.
- [x] Negative validation tests: unregistered `dataset_id`, unregistered metric, host not in registry, `http` without `allow_insecure`, `ADMISSION_REQUIRED` result shape (ADR-022 §2).

**Do not.** Write fetch or persistence code. Do not fetch from the network.

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md (§2 ADR-005, ADR-011, ADR-013; §4.1), docs/adr/ADR-017 … ADR-020 and ADR-022, ADR-023, ADR-026, ADR-027, docs/01-data-scope.md, docs/reviews/2026-09-19-codex-review-response.md, and docs/03-roadmap.md Phase 1. B-1, B-2, B-3, B-6 are resolved; implement them as amended. Author docs/04-contracts.md and implement the contracts package (observation, registry, hosts, manifest, parser protocol) with the property and negative tests. Stop when the six example manifests validate and the DST tests pass.

---

## Phase 2 — Platform core library

**Goal.** The platform owns semantics end to end, runnable locally on fixtures. **Done 2026-09-20** (`docs/plans/phase-2.md`, `docs/progress.md`), including the S3 Bronze backend (ADR-032 Option B, plan Task 2.10).

**Deliverables.**
- [x] `fetch/` — declarative fetchers per modality (httpx, timeouts, capped backoff with jitter, conditional requests, host-allowlist enforcement before any request).
- [x] `bronze/` — blob store (SHA-256 keyed) + capture log; `content_changed` detection; S3 backend (MinIO locally) *(2026-09-20: `bronze/s3.py` over the SigV4 client `fetch/objectstore.py`, ADR-032 Option B; MinIO ×2 is first exercised live in Phase 5)* and an in-memory backend for tests; read path tries hot then cold and the capture log carries `tier` (ADR-021).
- [x] `parse/` — generic parsers: html-table, xlsx, xml/soap, json-path, csv.
- [x] `mapping/` — executes the manifest `mapping` block: units, timezone, interval convention, sign convention → `EnergyObservation`.
- [x] `silver/` — Postgres schema and migrations (Alembic); bitemporal idempotent upsert per ADR-018; current-view. **Definition of done: every migration ships a downgrade script, exercised in CI (ADR-016 §3).**
- [x] `ledger/` — the run ledger (ADR-003 rev. as amended by ADR-024): `runs` (`target_id`, `scheduled_for`, `state`, `fence`, `origin`, latest lease) and `run_attempts` (`kind`, `lease_owner`, `lease_until`, `fence`, `capture_id`, `derivation_id`, `outcome`) migrations; `derivations` table (ADR-023); fenced claim/renew/commit; `reconcile(target, window)` from Bronze; missed-run query. Silver rows carry `run_attempt_id` and `derivation_id`.
- [x] `replay`, `backfill` and `gap_detector` modules (ADR-003 rev./ADR-004/ADR-024): gap detector emits `missing_capture` (→ backfill if within `history.max_age`, else `unrecoverable` + alert) and `unprocessed_capture` (→ replay); `replay --derivation <bad>` for ADR-016 §4 repair. Replay never fetches; backfill does.
- [x] Proofs (offline): the six ADR-023 replay/idempotency proofs and the ADR-024 crash matrix, one test each.
- [x] `energyctl` CLI: `validate`, `capture`, `process`, `replay`, `gaps`, `demo` *(plus `backfill`, `migrate`; commands take `--manifest` until the Phase 3 scaffolder, P2-D9)*.
- [x] `make demo`: fixture → capture → Bronze → parse → map → Postgres → query, offline. **Definition of done for the phase is this narrow complete path**; generic parsers beyond those the committed targets need (html-table, json-path, csv) may be stubs that fail loudly until Phase 4 needs them.
- [x] ADR for D-2 (Postgres *engine*: plain vs TimescaleDB) written before the schema is created. The DSN contract and `postgres.mode` are already decided (02 §4.2 D-2, 2026-09-19). *(2026-09-20: ADR-030, plain PostgreSQL ≥ 16; ADR-031 records the D-4 default the gap detector implements.)*

**Do not.** Add a target under `targets/` yet — use the Phase 1 example manifests with recorded fixtures only. No Kubernetes.

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md, docs/adr/ADR-003-rev-orchestration-without-crds.md, ADR-016, ADR-023, ADR-024, ADR-026 (fetch layer), docs/04-contracts.md and docs/03-roadmap.md Phase 2. Plan into docs/plans/phase-2.md. Implement the library in the order fetch → bronze → parse → mapping → silver → ledger → replay/gaps → CLI, committing per module with tests. Every migration has a downgrade script. `make demo` must run offline. Stop when it does.

---

## Phase 3 — Harness

**Goal.** Make the wrong thing impossible for both a junior and an agent. This is the deliverable the assignment is actually grading.

**Deliverables.**
- [x] `docs/05-constraint-matrix.md`: table `failure mode → gate → test that proves the gate`. Minimum rows: hardcoded URL; naive datetime; swallowed exception; unbounded retry; positional parsing; duplicated utility; new dependency; PR touching outside `targets/<id>/`; missing fixture; missing golden; missing `license`; host not in allowlist; secret in code; fetch code inside a target; normalise code inside a target; **outbound HTTP outside `energy_platform.fetch`** (A-7); **workload without resource requests** (A-8); **mutable image tag** (ADR-016); **migration without downgrade** (ADR-016); **unregistered `dataset_id` / metric / host** and **registry edit inside a target PR** (ADR-022); **file outside the target surface**, **third-party import in `parser.py`**, **suppression comment in a target**, **network call in a unit test** (ADR-027 — gates already exist from the review-1 remediation; the matrix rows and negative PRs are added here); **redirect to private/unlisted host**, **`http` scheme**, **metadata address** (ADR-026 §4, offline with a fake transport).
- [x] `energyctl new-target <id> --modality <m>` scaffolder (manifest skeleton, fixture dir, golden test skeleton, README stub, empty `__init__.py` files — exactly the ADR-027 surface).
- [x] `energyctl validate <id>` returns `ADMISSION_REQUIRED` with the missing registry entries when the manifest names an unregistered dataset/metric/host; `docs/admissions/TEMPLATE.md` for the Route B request (ADR-022).
- [x] `energyctl record-fixture <id>` (captures into `targets/<id>/fixtures/` as Bronze objects; opt-in network).
- [x] MCP server (`energy_platform/mcp/`) exposing the ADR-007 tool set as thin wrappers over the library. Sandbox recipe (`deployment/sandbox/`): container with no shell tool access, egress limited to the Git remote. *(2026-09-20: JSON-RPC 2.0 over stdio on the standard library, P3-D1; `open_pr` prepares a bundle that `scripts/apply_pr_bundle.py` turns into a branch outside the sandbox, P3-D2.)*
- [x] CI gates for every row of the constraint matrix; a target-PR path check (`targets/<id>/**` only).
- [x] Contract-test harness auto-discovers every target and runs its goldens; a target without fixtures/goldens fails collection *(2026-09-19: default collection of `targets/**/tests` already holds — `tests/harness/test_target_collection.py`)*.
- [x] Negative tests: `tests/harness/` contains one intentionally bad target per failure mode and asserts the correct gate rejects it.

**Do not.** Weaken a gate to make a negative test easier. Do not implement the drift-triage LLM step here.

*(2026-09-20: Phase 3 closed — `docs/plans/phase-3.md`, 05 rows C-01…C-54 each with a gate and a negative test; `tests/harness/test_matrix.py` keeps the table honest. Deferred with a reason in 05 §5: custom `parser.py` execution (loader needs an ADR amending ADR-027), layer-1 NetworkPolicy verification and the restricted-PSS check (Phase 5).)*

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md (ADR-005 to ADR-008), docs/04-contracts.md and docs/03-roadmap.md Phase 3. Write docs/05-constraint-matrix.md first. Then implement scaffolder, MCP server and CI gates so that every matrix row has a mechanical gate and a negative test. Stop when all negative tests are rejected by their mapped gate.

---

## Phase 4 — Committed-target verification through the harness

**Goal.** The harness's first real workload. Agents "look around" at Level 1 authority only. Scope is `01-data-scope.md` §3, nothing more. *(2026-09-19: list reduced from the 01 v0.1 catalogue to the v1.0 commitments.)*

**Deliverables.**
- [x] ADR for D-5 (cadence/politeness per 01 §5). D-11 is resolved "out" in 02 §4.2. *(2026-09-20: ADR-033 — `cadence.correction`, `next_delivery_day`; the re-capture verb is a Phase 5 task. ADR-034 `mapping.ignore_fields` closed the 04 §5 display-column question on the way.)*
- [x] **ČEPS interval labelling verification (review F13):** confirm from the ČEPS interface description (or an independent reference) that `@date` with `agregation=QH`, `function=AVG` labels the interval **start**; until confirmed the T3 manifest carries `interval_label: start` with an `[UNVERIFIED]` note and the goldens are not authoritative. Record the outcome in `docs/06-source-verification.md`. *(2026-09-20: **start** — HR/QH and DY/QH consistency on the live service; the interface description v3.2 was obtained and is silent on the edge. `docs/06` §4.4.)*
- [x] **Evidence index (review F12):** `docs/evidence/README.md` listing every source read used by `01` §3 (request shape, observation time, source/version, digest, bounded extracted facts, synthetic-fixture policy). Regenerated from the bounded live reads of the polling campaign if the original `message-board/evidence/` ledger is not supplied; raw captures are **not** committed until redistribution is confirmed. *(2026-09-20: 24 rows, regenerated from this session's reads; payloads outside the repository.)*
- [x] Committed targets, each via `energyctl new-target` → `record-fixture` → goldens → PR: *(2026-09-20: four Route A branches `target/<id>`, each one commit produced by `energyctl pr-bundle` + `scripts/apply_pr_bundle.py`, `make check` and `make pr-surface BASE=main` green; merging is Level 3 and is the maintainer's. `phase-4/all-targets` proves the union.)*
  - `ote_intraday_market` (T1, SOAP `GetImPricePeriodE`, system of record for `price_vwap`/`volume_total`) — 11 fixtures / goldens
  - `ote_intraday_market_xlsx` (T2, HTML discovery → daily XLSX; supplies buy/sell volumes and min/max/last; reconciliation rules of 01 §3 implemented as quality events) — 9
  - `ceps_load` (T3, SOAP `Load`, QH/AVG/RT only) — 9
  - `ote_dam` (E1, SOAP `GetDamPricePeriodE`) — **added last, by the contributor workflow, as the adapter-addition demo** — 7, built through the MCP server (`docs/06` §5.1)
  - `epex_intraday` as a `license: restricted` stub that the scheduler refuses (negative demo). *(2026-09-20: done as the Route B refusal — `docs/admissions/epex_intraday.md` from `energyctl admission-request`; no directory under `targets/` because an incomplete target fails collection by design. The "scheduler refuses `license: restricted`" rule moves to the Phase 5 CronJob renderer.)*
- [x] Candidates from 01 §4 (`ote_imbalance_settlement`, `ote_ida`, ČEPS generation/flows/imbalance/balancing, ENTSO-E class-B adapters, gas) are **not built**; each needs a 01 §3-style contract, a bounded live read and a §10 admission row first.
- [x] Fixtures per 01 §7 and §9: ordinary day, 23-hour day, 25-hour day, native hourly sample, partially filled day; negative and zero prices, absent `Price`, empty `<Result/>`, decimal-comma string, extra column, changed unit header; *(F13)* a complete day containing a legitimate no-trade NULL, a rolling partial day, an unchanged completed payload (stale fetch), a SOAP fault carried over HTTP 200, and a source-side 5xx versus a local failure with distinct status fields. Repository fixtures are **synthetic copies of the real shape** (01 §10) until redistribution is confirmed. *(2026-09-20: all as fixtures + goldens except the stale fetch and the 5xx-versus-local case, which are capture-level behaviour covered by platform tests named in each target README.)*
- [ ] One-week polling observation per target (01 §5) → publication latency recorded before any figure is quoted. *(2026-09-20: procedure defined in `docs/06` §6, **not run** — needs seven days of wall clock; no figure quoted.)* **Closed without running (author decision 2026-09-23: delivery before a week of wall clock).** No latency figure is quoted anywhere; the live demo's capture log keeps the observations for whoever runs `docs/06` §6 later. *(Phase 9: an 11-hour observation from the demo is in `docs/06` §6.1, stated as one day's upper bounds on the polling grid, not as the week.)*
- [x] `docs/06-source-verification.md`: per source — endpoint verified, auth, rate limits observed, terms-of-use notes (V-1, V-3), quirks (decimal comma, DST rows, progressive fill), T1/T2 reconciliation mismatches seen. *(2026-09-20: 0 mismatches in 346 periods.)*
- [x] Nightly live-smoke workflow definition (not run in PR CI). *(2026-09-20: `tests/live/test_smoke.py`, `make live-smoke`, `.github/workflows/nightly-live-smoke.yml`; run once by hand on `phase-4/all-targets`: 4 passed.)*

**Do not.** Edit `energy_platform/` in a target PR. If a source needs a platform change, open a separate PR with an ADR. Do not scrape anything without `license`/`terms_url` filled from the source's own terms page.

**Starter prompt.**
> Read CLAUDE.md, docs/01-data-scope.md §3, §5, §7, §9, §10, docs/04-contracts.md, docs/05-constraint-matrix.md and docs/03-roadmap.md Phase 4. For T1, T2, T3 in that order: scaffold with energyctl, verify the live endpoint once, record a fixture, write goldens with values you checked by hand against the fixture, and open a PR touching only targets/<id>/. Then add E1 strictly through the contributor workflow as the adapter-addition demo. Do not add any 01 §4 candidate. Record findings in docs/06-source-verification.md. Stop when all four pass contract tests offline.

---

## Phase 5 — Deployment, IaC, HA, DR, observability

**Goal.** Reproducible by the evaluator; resilient by the ADR-004 invariants; measurable by ADR-012.

**Deliverables.**
- [x] ADRs for D-1, D-3 (D-4 was resolved by ADR-031 in Phase 2; D-6, D-7 are contracts in 02 §4.2; D-8 is resolved by ADR-021) and ADR-012 written. *(2026-09-22: ADR-035 own-cluster stack, ADR-036 object stores and backups per profile, ADR-037 freshness SLI.)*
- [x] Helm chart `deployment/helm/energy-platform` *(2026-09-22: `make helm-lint` renders tenant, local and all-flags values through digest/resources and restricted-PSS checkers; 05 C-55…C-57.)* (core = `tenant`-clean, no CRDs, `restricted`-PSS-clean, requests/limits on every workload): **`CronJob` template rendered once per target** from `targets/*/manifest.yaml` (capture, process), gap-detector `CronJob`, **hook chain per ADR-025** (`migrate` = `post-install,pre-upgrade` weight −10; `storage-probe` = `post-install,post-upgrade` weight −5 when `bronze.tiering.mode=lifecycle`; `smoke` = `post-install,post-upgrade,test` weight 0), Postgres per `postgres.mode` (`statefulset` \| `cnpg` \| `external`), MinIO ×2 (local), **NetworkPolicies per ADR-026 layer 1** (default deny; DNS/Postgres/object store; TCP 443 to public ranges with private/metadata `except` blocks for capture and backfill pods only; `egress.fqdnPolicy` optional), plain `Secret` by default with ESO behind `secrets.eso.enabled`, `/metrics` annotations with `PodMonitor` behind `metrics.operator.enabled`.
- [x] **Upgrade gate** *(2026-09-22: `migrate` and `smoke` hooks pass inside `helm upgrade --install --rollback-on-failure --wait --wait-for-jobs` on kind; Helm 4 spells `--atomic` as `--rollback-on-failure`.)* (ADR-016 as amended by ADR-025): the `smoke` hook Job runs one fixture capture+process end-to-end against the new image *inside* `helm upgrade --install --atomic --wait --timeout`, which is the command in every deploy Make target; `helm test` re-runs the same Job on demand; images by digest only. *(2026-09-19: "`helm test` hook" was not an upgrade gate — review F07.)*
- [x] **Rollback drill** *(2026-09-22: `make rollback-drill` — failing smoke and failing storage probe both roll back; `.github/workflows/weekly-drills.yml`; the smoke writes no production Bronze, so the assertion is "production untouched", plan P5-D13.)* (ADR-016 §6, ADR-025 §5): scheduled job deploys revision N, then N+1 with (a) a parser that fails the smoke fixture and (b) a failing storage probe; asserts for each: previous revision active, schema unchanged and compatible, Bronze captures of the failed attempt present and reconciled.
- [x] `deployment/local/`: `make local-up` *(2026-09-22: kind + Cilium + kind-attached registry; all three egress assertions PASS.)* = kind **with a policy-enforcing CNI** (Calico or Cilium in policy-only mode; kindnet does not enforce `NetworkPolicy`, ADR-026 §4) → Helm deps → Helm platform (hooks run migrations and smoke) → egress test (legitimate capture succeeds; pod → metadata address and pod → private address blocked; process pod has no internet).
- [x] **V-11** (ADR-026): does the reference tenant CNI enforce egress `NetworkPolicy`? Record in `00` §5; until CONFIRMED the tenant profile documents layer 1 as "declared, enforcement unverified". One-off probe on the reference cluster; it informs the scenario-A claim, not the demo. **Closed without running (author decision 2026-09-23):** the tenant profile documents layer 1 as "declared, enforcement unverified" (`docs/threat-model.md` §6); the fetch layer is the control known to hold. **Run after all (Phase 9, 2026-09-23): CONFIRMED** — the reference cluster's Calico enforces egress policy for a tenant namespace (`00` §5). The same test on the demo found kube-router applying a new pod's policy after the pod starts; the chart gained a policy gate (ADR-026 amendment 2, `05` C-65).
- [x] *(2026-09-22, all three CONFIRMED in `00` §5)* **V-12, V-13, V-14** (ADR-028): Hetzner Object Storage (versioning, Object Lock, storage-class probe as V-6); OCI Object Storage S3-compat endpoint (versioning, retention rule enforced, `rclone` A → B round-trip); k3s structured authentication with the GitHub Actions OIDC issuer (namespace rights only). Run by the author, raw output into `00` §5, **before** the Terraform and replication tasks below start.
- [x] **Cost guard** *(2026-09-22: ceilings and checklist in `deployment/own-cluster/README.md`; the console budget alerts are the author's step before `apply`.)* (ADR-028 §5): budget alerts on both accounts (Hetzner €25/month, OCI €10/month) and ceilings written into `deployment/own-cluster/README.md` before the first `terraform apply`. `apply`/`destroy` and bucket deletion are author-run (Level 3); the agent produces `terraform plan -out` only.
- [x] `deployment/tenant/`: values for a namespace-only deploy *(2026-09-22: `values-tenant.yaml`, `values-demo.yaml`, OIDC deploy workflow and `make deploy-demo` delivered; the demo deploy itself waits on the author: `terraform apply`, GitHub remote, repository variables, the Secret — docs/07 §4. 2026-09-23: four hand-over blockers fixed — the workflow builds and pushes the amd64 image itself, demo values without placeholders, a pull secret for the private package, the backup footprint bounded by ADR-036 amendment 1; the GitHub repository exists; the author's steps are `apply`, two variables, two Secrets, one run. Later on 2026-09-23 the agent ran those steps at the author's request: **the demo is live** — GitHub OIDC deploys into the namespace Role, captures run every 15 minutes, and a restore drill from OCI store B matched live; six defects the first real apply exposed are fixed with tests, docs/07 §4.1.)*; **`values-demo.yaml` deployed into a namespace-scoped `Role` on the demo cluster (ADR-028) as the first real environment**; the reference cluster (e-INFRA Rancher, `00` §5 V-4) hosts no release and no scheduled workload; deploy identity per the ADR-015 federation clause (GitHub OIDC → k3s structured authentication, V-14; fallback = namespace-scoped token with expiry recorded). *(2026-09-19: was "deploy to the reference cluster"; changed by ADR-028 — academic terms of use.)*
- [x] `deployment/own-cluster/terraform/` *(2026-09-22: four modules × two variants, both roots validate and pass `terraform test` with mocks; `hcloud` planned — 12 to add — never applied.)*: shared modules (`network/`, `nodes/`, `storage/`, `security/`) and one cloud-init that installs k3s (D-1 — Magnum is absent on the reference cloud, `00` §5 V-5); **two roots**: `openstack/` (reference; sized to the verified quota 20 vCPU / 50 GB RAM / 1 floating IP; `terraform test` with mocks in CI, never applied) and `hcloud/` (demo, ADR-028: 2× `cx23` (`cx22` no longer exists, V-14), private network, firewall 443 in + 6443 per ADR-035 §4, one Postgres volume; applied by the author). Both roots pass `terraform validate` and `terraform test` in CI.
- [x] Backups: pgBackRest/WAL-G *(2026-09-22: base backup + WAL archive shipped by `rclone` (ADR-036 amends the tool), whole-bucket A → B replication verified, restore drill passed on kind: PITR from store B and a Bronze-only rebuild both match live — docs/07 §5.)* to object store; Bronze replication as an `rclone` job to the independent endpoint (**demo: store A Hetzner Object Storage → store B OCI Object Storage Frankfurt, another provider and country, ADR-028 §3, V-12/V-13**; the S3 → Swift record on the reference environment, `00` §5 V-6, stays as the drill that shaped the design); `residency` asserted as `DE` in the demo values (ADR-028 §4); **`bronze-tier` CronJob** per ADR-021 (`bronze.tiering.mode = none|move|lifecycle`) with the storage-class **probe as the `storage-probe` hook** (ADR-025; a gateway that answers `400 InvalidArgument` or reports STANDARD fails the upgrade); **restore drill** as a scheduled `CronJob` with assertions, including a replay that reads from the cold location and a ledger rebuild by `reconcile` over the full history (ADR-024 §2).
- [x] Observability: freshness SLI *(2026-09-22: ADR-037; `target_freshness` + `postgres_exporter`, alert rules, dashboard JSON; scraped on kind.)* per target, `source_unavailable` vs `pipeline_failed`, alert rules, Grafana dashboard JSON.
- [x] `make smoke-test` *(2026-09-22: `helm test` + freshness metric + restore-drill dry run.)*: cluster up, one capture+process run on a fixture target, freshness metric present, restore drill dry-run.

**Do not.** Put any LLM component in the Helm chart's critical path. Do not require credentials for the local profile.

**Starter prompt.**
> Read CLAUDE.md, docs/00-assumptions.md, docs/02-architecture-decisions.md (ADR-001 to ADR-004, ADR-012, ADR-016), docs/adr/ (ADR-028 for the demo environment), docs/03-roadmap.md Phase 5. Confirm V-12, V-13, V-14 are filled in `00` §5; if not, stop and ask the author to run them. Write the D-* ADRs first. Then build the Helm chart and local profile until `make local-up && make smoke-test` passes from a clean clone; then the own-cluster Terraform roots (`openstack` mock-tested, `hcloud` planned — the author applies); then deploy the tenant values into the demo cluster's namespace; then backups, the cross-provider Bronze replication, the restore drill and the rollback drill; then observability. Never apply Terraform, never delete a bucket, never leave a release on the reference cluster. Stop when all gates pass.

---

## Phase 6 — Threat model, triage pipeline, documentation

**Deliverables.**
- [x] `docs/threat-model.md` complete: each ADR-008 catalogue item with mechanism, gate, residual risk. *(2026-09-23: 10 ADR-008 items + 5 repository items, every cited test checked.)*
- [x] Drift-triage pipeline (D-10): contract-test failure → bounded extractor → `LLMBackend` (stubbed by default) → patch proposal → PR. Prompt-injection test cases in `tests/triage/` (hostile HTML fixtures must not alter the proposed patch beyond the manifest). *(2026-09-23: `energy_platform/triage/`, `energyctl triage`; 19 tests incl. 10 answers from a model that obeys the injection; 05 C-58…C-61; an import contract keeps triage off the capture/process path.)*
- [x] `docs/08-adding-a-target.md` *(numbered 08: 07 is the operations runbook, plan P6-D2)*: the junior's page. Must be sufficient on its own for Phase 7, and must explain both routes of ADR-022 (adapter addition; admission request when `energyctl validate` says `ADMISSION_REQUIRED`).
- [x] **Held-out admission (ADR-022 §3):** the maintainer admits one `01` §4 candidate through Route B (registry entries, host registry, `01` §10 row; no adapter). This is the Route B demonstration and the input to Phase 7 run 1. *(2026-09-23: OTE imbalance settlement, `ote.imbalance_settlement` — `docs/admissions/ote_imbalance_settlement.md`; no adapter.)*
- [x] Architecture diagram (Mermaid in `docs/architecture.md`).

**Starter prompt.**
> Read CLAUDE.md, docs/02-architecture-decisions.md (ADR-007 to ADR-009), docs/05-constraint-matrix.md, docs/03-roadmap.md Phase 6. Complete the threat model, implement the triage pipeline with the LLM stubbed, write docs/07-adding-a-target.md as if for someone who has never seen this repository. Stop when the prompt-injection tests pass.

---

## Phase 7 — Blind acceptance tests

**Protocol** *(2026-09-19: rewritten per ADR-022 after review F04 — the earlier version scored a legitimate escalation as failure)*.

Run 1 — **adapter addition (Route A).** New Claude Code session, **`/clear`**, no prior context. Provide only `README.md`, `docs/08-adding-a-target.md`, and the URL of the source **pre-admitted in Phase 6** (contract and `01` §10 row exist; no adapter). Instruction: "Add this as a target and open a PR." Nothing else. Expected: PR touching only `targets/<id>/`, green CI, goldens checked by hand. Record files touched, CI result, whether `energy_platform/` was modified, number of turns.

Run 2 — **escalation (Route B trigger).** Same setup with the URL of an **unadmitted** class-A source (e.g. an Open-Meteo endpoint). Expected: an admission request (`docs/admissions/<id>.md`) and nothing else. Any registry edit, invented unit or widened allowlist is a defect of the run; a fabricated pass is a Phase 3 defect (the gate that should have caught it).

Run 3 — **junior path.** Repeat run 1 via the CLI golden path following `docs/08-adding-a-target.md` literally, as a junior would (no MCP).

Write `docs/09-acceptance-report.md` with all runs *(numbered 09 since 2026-09-23, plan P6-D2)*. If run 1 or run 3 required a core change or human architectural guidance, that is a Phase 3 defect: fix the harness, not the report. If run 2 stopped with a correct admission request, that is a pass.

- [x] Run 1 (adapter addition) recorded *(2026-09-23: PASS — PR #1, target-only, CI 12/12, 45/45 golden rows re-derived)*
- [x] Run 2 (escalation) recorded *(PASS — PR #2, the admission request only; flags Open-Meteo's non-commercial API terms)*
- [x] Run 3 (junior path) recorded *(PASS — PR #3, CLI only, target-only, CI 12/12, 32/32 golden rows re-derived)*
- [x] Defects fed back and closed *(F-1 contributor sessions vs the maintainer protocol, F-2 `AGENTS.md` drift — closed with a test in f7c77d1; F-3 memory not perfectly blind, F-4 one version per target: recorded)*

---

## Phase 8 — Submission packaging

- [x] `README.md`: what it is, 5-line reproduce block (ADR-010), architecture diagram, how targets are added, how agents are constrained, what was deliberately not built and why (link to §4 defaults not implemented), and a section **"Assumptions and what they cost"** summarising `00-assumptions.md` §2 (reference environment, scenarios A/B/C, each assumption's cost if false, verification verdicts). The reproduce block gains **"or open the live demo"** (ADR-028): URL, how read-only evaluator credentials are handed over out of band, what the demo shows (captures landing, freshness SLI, a restore drill run), and the demo's declared deviations (`residency: DE`, two-node k3s without control-plane HA).
- [x] `docs/ci-porting.md` stub: how to port the GitHub Actions wrappers to GitLab CI (ADR-015, A-13).
- [x] `docs/` index; ADR log complete; progress log trimmed. *(2026-09-23: `docs/README.md`, `docs/adr/README.md`, entries before Phase 5 moved verbatim to `docs/archive/`.)*
- [x] Final clean-clone run on a machine that has never seen the repository. *(2026-09-23: fresh Ubuntu 24.04 VM; two findings fixed — libpq prerequisite, `smoke-test` under Make 4.x `-e`; then `make check` 815 passed and `local-up && smoke-test` exit 0 in 199 s — `docs/07` §8.1.)*

---

## Phase 9 — Gap closure

**Goal.** Close every gap still open after Phase 8 before delivery (2026-09-24): security and CI residuals first (P1), then evidence and recorded findings (P2), then optional items (P3). A P3 item that is not built goes into the README table "Deliberately not built" with its reason. Plan: `docs/plans/phase-9.md`.

- [x] P1 — deploy identity pinned to the workflow, deployer `Role` without `secrets`/`exec`, no server replacement (G1); `secretRef` scoped per target (G2); fetch response-size cap (G3); `uv` bootstrap by checksum (G4); `weekly-drills` green on GitHub (G5); `deploy-demo` on push to `main` (G6).
- [ ] P2 — V-11 probe on the reference cluster (G7); an N-hour publication observation from the demo (G8); settlement versions 1 and 2 as Route A targets on a month-offset render capability (G9, `09` F-4); a strictly blind re-run (G10, `09` F-3); review-1 F09/F12 closed in the response document (G11). *(Done: G7 V-11 CONFIRMED plus the demo's policy gate; G8 11-hour observation; G9 the month capability on `main` and version 1 as PR #4, reviewed and merged 2026-09-24 (d14388c, demo revision 8); G11. G10 the strictly blind re-run: run by the author 2026-09-24 in an empty profile, PR #5 target-only 12/12 with 0 interventions, evaluated as `docs/09` run 4 — PASS, F-3 closed; #5 merged c81f34c, demo revision 9, F-4 closed in full.)*
- [x] P3 — as far as time allows (G12 … G18); the rest in the README with reasons. *(Built: G15 sandbox-image test, G16 Hetzner console check, G17 branches, G18 email drafts (not sent). Not built, with reasons in the README: G12, G13, G14.)*
- [x] Final clean-clone run on a throwaway VM; threat-model residuals reduced to what remains. *(`docs/07` §8.2.)*

---

## Phase 10 — Correctness and recovery (review 2) — done 2026-09-24

**Goal.** Make the platform's output correct through every correction, overlap and recovery it promises: the eight P1 and nine P2 findings of the final external review (`codex-review/2026-09-24/`, response in `docs/reviews/2026-09-24-codex-review-response.md`). Tasks 10.1–10.10, their ADR amendments and acceptance tests are in `docs/plans/review-2.md`. Done 2026-09-24 ahead of it: the review committed and answered, DEP-04 (fail-open external Postgres rule), AE-03 (bundle names what it did not run), the two editorial errors, the README completion statement bounded.

- [x] 10.1–10.2 owner-aware current view and occurrence lineage (ADR-023 amendment; DC-03, DC-04)
- [x] 10.3–10.5 capture generations, replay reclaim, collision-safe capture log (ADR-024 amendment; DC-01, DC-02, DC-05, DC-06)
- [x] 10.6 durable invalidation decisions applied by replay, restore and the drill (ADR-038; DC-07); the 22 September row recorded by the author
- [x] 10.7 target-scoped freshness (ADR-037 amendment; DC-08)
- [x] 10.8 RPO per failure domain, replication interval or amended bound, replica-age alert (ADR-036 amendment; DEP-01)
- [x] 10.9 deployment modes refuse what they do not implement; Cilium FQDN rule; policy-gate readiness (DEP-02, DEP-03, DEP-05)
- [x] 10.10 contributor path: triage inventory, plain-Git primary route, MCP admission request, custom parser refused until loadable (AE-01, AE-02, AE-04)

---

## Phase 11 — Grafana dashboards over Silver (private) — done 2026-09-24

**Goal.** A window onto the collected data and the platform's health without a public endpoint (ADR-039): Grafana behind a chart flag, a read-only database role, two provisioned dashboards over the current views, access by port-forward. Plan: `docs/plans/phase-11.md`.

- [x] 11.1 migration `0007_reader_role`, `energyctl migrate --reader-user` (db-test: SELECT yes, INSERT no)
- [x] 11.2 chart component, network policies, hook step, dashboards, local and all-flags values (chart tests, helm-lint)
- [x] 11.3 ADR-039, `07` §7.1, README, `05` C-70
- [x] 11.4 demo: Secret keys, `grafana.enabled`, deploy, a port-forward render

## Phase 12 — the local profile's object stores after MinIO — done 2026-09-24

**Goal.** Restore the clean-clone gate: MinIO's community images were withdrawn on 2026-09-24 (`07` §8.3), so the `local` profile's two stores and the `mc` init job are replaced by an S3 server that exists and passes an empirical Object Lock probe (ADR-036 amendment 4). Same semantics as the demo's stores; nothing else changes. Plan: `docs/plans/phase-12.md`.

- [x] 12.1 probe the candidates in Docker (RustFS 1.0.0 passes all 23 steps; `07` §8.4)
- [x] 12.2 `fetch.objectstore` bucket verbs, `energyctl bucket-init`, fake-gateway support, tests
- [x] 12.3 chart: `objectstore.yaml` (RustFS by digest), `hook-bucket-init.yaml` on the platform image, values, `local-secrets`, chart test
- [x] 12.4 ADR-036 amendment 4, ADR-032 pointer, `07` §2 and §8.4, local README, README, `05` C-71
- [x] 12.5 the gate: `make local-down && make local-up && make smoke-test`, `make rollback-drill`, a live capture COMPLIANCE-locked in RustFS A, Grafana on kind — all PASS (`07` §8.4)

## Phase 13 — review 3 (codex-astra, 2026-09-25) — done 2026-09-25

**Goal.** Answer the six findings of `codex-review/` the way review 2 was answered: rerun the probes (all four reproduce on memory and PostgreSQL), close each runtime defect with the reviewer's counterexample as a negative test, each design gap by an ADR amendment, wire the alert path the rules assumed, state the availability boundary, revise the final report. Plan: `docs/plans/phase-13.md`; response: `docs/reviews/2026-09-25-codex-review-response.md`.

- [x] 13.0 the review verbatim (the earlier rounds archived by the reviewer), ruff scoped to the source tree, the plan, the response
- [x] 13.1 the four probes rerun on the temporary PostgreSQL: every one reproduces (exit 0)
- [x] 13.2 R2: `runtime/schedule.py`, `capture --live` keyed by the schedule's instant (the CronJob's tick by the downward API), ADR-031 amendment 1, six negative tests
- [x] 13.3 R4: `implementation_version()` in the derivation identity, ADR-023 amendment 3, negative tests on both stores
- [x] 13.4 R5 + R6: the drill rebuilds the cohort first, lineage-scoped value fingerprints, `missing` / `diverging` / `historical`, ADR-036 amendment 5, negative tests on both stores (a cursor defect only PostgreSQL showed, fixed)
- [x] 13.5 R3: `alerting.enabled` — Prometheus over the existing rules, namespaced kube-state-metrics, Alertmanager, `energyctl alert-sink`, Grafana datasource; ADR-040; chart and sink tests; `make alert-drill`
- [x] 13.6 the delivery drill on a fresh kind cluster (`07` §7.2)
- [x] 13.7 ADR-028 amendment 1 (R1), `05` C-72…C-75, `07` §5 and §7, README, chart and tenant READMEs, `02` pointer, the final report rewritten to the assessment, roadmap, progress

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
- A target PR touches only targets/<id>/ (the ADR-027 surface). Anything else is a platform PR.
- Registry entries (dataset, metric, host) are platform PRs (ADR-022); an unadmitted source gets an admission request, not an invented unit.
- Timezones: every datetime is aware; delivery intervals are tstzrange; DST days have 92/100 intervals.
- All outbound HTTP goes through energy_platform.fetch. Images by digest. Every migration has a downgrade.
- The core Helm chart needs no CRDs and passes the restricted Pod Security profile.
- Decimal comma is common in Czech sources; parse explicitly, never float() on raw strings.

## Authority
Level 0 read · Level 1 generate targets · Level 2 propose PRs · Level 3 forbidden:
merge to main, production secrets, terraform apply, kubectl write, prod DB mutation, archive deletion.
```
