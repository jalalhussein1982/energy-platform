# Progress log

One dated entry per session. Newest first.

---

## 2026-09-19 — ADR-028: demo environment (docs only, no platform code)

**Why.** Roadmap Phase 5 had the tenant profile running for real on the e-INFRA Rancher cluster. e-INFRA CZ terms cover research and education; this is a commercial deliverable, so a scheduled workload there is out of policy. One-off probes (V-4 … V-10) stay.

**Decided** (`docs/adr/ADR-028-demo-environment.md`, ACCEPTED): three environment words — *reference* (MetaCentrum, probes only, no release), *demo* (author-paid, handed to the evaluator live), *production* (ČEZ). Demo = Hetzner Cloud two-node k3s built by the `own-cluster` Terraform through a new `hcloud` root sharing modules with the `openstack` root, deployed with `tenant` values into a namespace-scoped Role so one cluster proves both profiles; Bronze store A on Hetzner Object Storage, store B on OCI Object Storage Frankfurt (S3-compatible endpoint, retention rule) — two providers, two countries, which is what A-3 means by independent. Residency declared `DE` on the demo. Budget alerts before the first apply; apply/destroy/bucket deletion stay Level 3 (author). Rejected: stay on MetaCentrum, OCI-only (free ARM tier halved 2026-06-15, capacity, multi-arch), Hetzner-only (one operator), OKE, a `demo` profile.

**Reconciled.** `02` ADR-001 paragraph and `tenant` bullet, §4.2 D-1/D-3, §4.3 V-11 … V-14; `00` §2.1 row, A-9 note, §4 V-12 … V-14, §6 checklist; ADR-001 amendment header; `03` Phase 5 (demo cluster, `hcloud` root, A → B replication, cost guard, V-12 … V-14 gate) and Phase 8 (live-demo block).

**Open, author-run before Phase 5 Terraform work:** V-12 (does Hetzner Object Storage support Object Lock?), V-13 (OCI retention + `rclone` A → B), V-14 (k3s structured auth with GitHub OIDC). Accounts exist: Hetzner project, OCI pay-as-you-go. Credentials outside the repository.

**Next.** Phase 1 (contracts), unchanged.

---

## 2026-09-19 — Review 1: Codex pre-coding verdict answered (docs + gates, no platform code)

**Input.** `codex-review/` (14 findings, 9 P1) against `7d872ea`. Verdict accepted: design checkpoint, not a submission; the executable gates were thinner than the documents claimed. Response per finding: `docs/reviews/2026-09-19-codex-review-response.md`; plan: `docs/plans/review-1.md`.

**Decided** (`docs/adr/`, all ACCEPTED): ADR-022 source admission vs adapter addition (two routes; escalation is a pass in Phase 7); ADR-023 derivation identity (version key gains `derivation_id`; `contract_version` ≠ implementation; current view by capture ordering basis then derivation); ADR-024 capture recovery (Bronze capture-log entry is the durable boundary, `reconcile` rebuilds the ledger, `run_attempts` + fencing at commit, backfill ≠ replay, `history.max_age`); ADR-025 upgrade hooks (`smoke` = `post-install,post-upgrade,test`; `migrate` = `post-install,pre-upgrade`; probe joins the chain); ADR-026 egress boundary (NetworkPolicy = coarse layer with private/metadata `except`; per-host, resolution and redirect checks in `fetch` against a CODEOWNERS host registry; V-11 added); ADR-027 target capability boundary (positive file and import allowlists for targets, extended banned-API list, unit-test socket block).

**Gates now real** (`make check` = lint + lock-check + type + test; 36 tests): `targets/**/tests` collected by default (pytester negative test); `scripts/check_target_surface.py` in `make lint` with 11 negative tests; ruff TID251 covers `http.client`, `socket`, `subprocess`, `importlib`, … outside `fetch/`; root `conftest.py` disables sockets unless `live`; secret-scan exempts the matched value, not the line (7 tests); `uv lock --check` in `check` and CI; hatchling, uv installer and `actions/checkout` pinned; pre-commit runs the same three gates as CI. Re-ran the reviewer's probes: the `http.client` parser fails lint, the planted failing target test fails the default run, a stale lock fails `lock-check`, the "token + # example" line is reported.

**Learned.** A gate that is only a ban list is bypassed by the standard library; a positive allowlist on the smallest surface (targets) plus a runtime block is what actually holds. `helm test` hooks are not part of `--atomic`. Standard `NetworkPolicy` has no hostnames. `--frozen` is not `--locked`. Three findings were premises, not code: "cannot ask the evaluator" was reworded to a choice.

**Blocked on the author.** F09: a Git remote and a real handle for `CODEOWNERS`, then apply `docs/branch-protection.md`. F12: the original `message-board/evidence/` ledger for the energy task was not found on this machine (the two message-board directories on disk belong to other projects); either supply it or let Phase 4 regenerate `docs/evidence/`.

**Not done, by design.** No Phase 1 code (one phase per session, 03 §0). `docs/01-data-scope.md` untouched; F13 (ČEPS interval labelling) is a Phase 4 verification task. `codex-review/` committed verbatim as evidence.

**Next prompt** (03 Phase 1 starter, as amended):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md (§2 ADR-005, ADR-011, ADR-013; §4.1), docs/adr/ADR-017 … ADR-020 and ADR-022, ADR-023, ADR-026, ADR-027, docs/01-data-scope.md, docs/reviews/2026-09-19-codex-review-response.md, and docs/03-roadmap.md Phase 1. B-1, B-2, B-3, B-6 are resolved; implement them as amended. Author docs/04-contracts.md and implement the contracts package (observation, registry, hosts, manifest, parser protocol) with the property and negative tests. Stop when the six example manifests validate and the DST tests pass.
```

---

## 2026-09-19 — Reconciliation of 02/03 with 01 v1.0 (docs only, before the pre-coding review)

02 and 03 had been written against 01 v0.1's wide catalogue. Corrected, each with a dated note: 02 §1.1 scope wording (intraday market results as the core; modality matrix = framework test suite, not live targets); ADR-002 capture-log field names follow 01 §6.1; ADR-005/ADR-013 fetch spec gains the declarative discovery step T2 needs and a `contract` block; ADR-011 points at 01 §6–§9 as source; ADR-012 freshness per 01 §5, "per tier" dropped; §3 step 4 and V-1 reworded; D-5 default = 01 §5 intervals; D-11 default → out. 03 Phase 1 example manifests (three real, two shape-only) and 04-contracts source; Phase 4 reduced to T1, T2, T3, E1 + the restricted stub, candidates explicitly not built, fixtures per 01 §7/§9, one-week polling campaign; Phase 7 unseen-source wording. CLAUDE.md/AGENTS.md/README scope line.

**Still open for the review:** `01-data-scope.md` cites `message-board/evidence/` (S01–S17) which is not in this repository — either add the evidence files or reword the citations before submission. 01 itself was not edited.

---

## 2026-09-19 — Phase 0: repository bootstrap — DONE

**Gate:** `make check` green on the empty package (ruff incl. egress ban, mypy --strict, import-linter 2 contracts kept, 1 placeholder test). Ten commits, one per task plus one fix.

**Delivered.** `pyproject.toml` (Python 3.12, uv, hash-pinned `uv.lock`, ruff DTZ/S110/S113/TID251 banned-api for httpx/requests/urllib/urllib3/aiohttp outside `energy_platform/fetch/`, mypy strict, import-linter layers); empty `energy_platform/` + `contracts/`, `targets/`, placeholder test; `Makefile` with `check/lint/type/test`, `deps-allowlist`, `secret-scan`, `helm-lint`, `terraform-validate`, `ci-bootstrap`, and honest stubs (`local-up`, `local-down`, `smoke-test`, `demo`, `new-target` exit non-zero with the phase that implements them); `deps-allowlist.txt` (31 packages, transitive included) + `scripts/check_deps_allowlist.py`; `scripts/secret_scan.py`; `.github/workflows/ci.yml` (7 jobs, every step is `make <target>`); `.pre-commit-config.yaml`; `CLAUDE.md` = `AGENTS.md`; `CODEOWNERS`; PR template; `docs/branch-protection.md`; `docs/threat-model.md` stub (10 headings); `README.md` stub; `.gitignore`.

**Verified.** Negative tests run by hand: a lock with `totally-hallucinated-pkg` fails `deps-allowlist` (exit 1, names it); a file with an AWS key-id pattern fails `secret-scan`; `helm-lint`/`terraform-validate` skip with exit 0 when their inputs are absent and fail with exit 1 when present without the tool (a first version continued past the skip; fixed in `ee8148c`).

**Learned.** ruff's S-rules caught the bootstrap scripts themselves (partial executable path, subprocess); kept the rules, fixed the scripts. Multi-line Make recipes run each line in a fresh shell, so a skip must be a single block.

**Not done / flagged.** `CODEOWNERS` has a placeholder handle; replace before branch protection. `scripts/check_restricted_pss.py` referenced by `helm-lint` is a Phase 5 deliverable (the target cannot reach it before the chart exists). No remote configured. `pre-commit` is in the dev group but not installed into `.git/hooks` (`uv run pre-commit install` when wanted). `energyctl` entry point deferred to Phase 2. D-2 engine choice still needs its ADR before the Phase 2 schema.

**Next prompt** (03 Phase 1 starter, verbatim):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md (§2 ADR-005, ADR-011, ADR-013; §4.1), docs/adr/ADR-017 … ADR-020, docs/01-data-scope.md, and docs/03-roadmap.md Phase 1. B-1, B-2, B-3, B-6 are resolved; implement them. Author docs/04-contracts.md and implement the contracts package with the property tests. Stop when the five example manifests validate and the DST tests pass.
```

---

## 2026-09-19 — Decisions session (no platform code)

**Verified** (`00-assumptions.md` §5; access: e-INFRA Rancher kubeconfig, MetaCentrum Cloud Brno1 application credential, CESNET S3, e-INFRA LLM; all credentials kept outside the repository):

| V | Verdict | One line |
|---|---|---|
| V-4 | CONFIRMED | Tenant only: no CRDs; CronJobs/NetworkPolicies allowed; `restricted` Pod Security enforced; ingressclass list Forbidden; Argo CRDs present but CronWorkflow create denied; CNPG, cert-manager, prometheus-operator creatable in-namespace; no External Secrets; quota 6/10 CPU, 5/9 GiB |
| V-5 | CONFIRMED | No Magnum in Brno1 catalog; quota 20 vCPU / 10 instances / 50 GB / 1 network / 1 floating IP; Ubuntu jammy+noble images |
| V-6 | CONFIRMED | S3 (Ceph RGW) versioning + object lock + lifecycle verified on store A; Swift on a separate Brno endpoint verified as store B; storage-class probe: only STANDARD exists, lifecycle accepts unknown classes silently → ADR-021 (tiering job) |
| V-7 | CONFIRMED | OpenAI-compatible endpoint, 34 models |
| V-8 | CONFIRMED | Federated (Shibboleth/Perun) identity; kubeconfig is an opaque Rancher token with 1-year TTL. Second pass: Rancher mints ≤ 5-min cluster-scoped tokens from an existing token (no tenant-creatable CI principal); SA TokenRequest JWTs are rejected by the Rancher proxy → two-token CI pattern (ADR-015) |
| V-9 | CONFIRMED | No proxy; OTE, ČEPS, ENTSO-E reachable from a pod |
| V-10 | CONFIRMED | No managed Postgres; CNPG operator pre-installed |

Register changes: A-5 cost-if-false updated; A-13 (GitHub Actions) and A-14 (`restricted` PSS) added.

**Decided** (`docs/adr/`, all ACCEPTED): ADR-001-amend (three profiles; MetaCentrum = reference environment), ADR-003-rev (CronJob + run ledger, no CRDs), ADR-014 (tooling), ADR-015 (GitHub Actions as thin wrapper over Make; A-13), ADR-016 (release and rollback), ADR-017 (manifest YAML/JSON Schema/directory convention/`secretRef`), ADR-018 (`tstzrange`, append-only versions, both timestamps), ADR-019 (five parsers, dependency allowlist), ADR-020 (Bronze fixtures, YAML goldens, Hypothesis, nightly smoke), ADR-021 (Bronze cold tier as a platform `rclone` tiering job with deploy-time probe; resolves D-8; filed after a follow-up storage-class probe the same day). `02` reconciled with superseded text kept; `03` Phases 0–3, 5, 8 and appendices reconciled; `00` §6 all ticked. No phase checkbox ticked.

**Contradictions found:** none against `00` §3. Two nuances recorded: (1) Argo is installed on the reference cluster yet unusable by a tenant, which strengthens ADR-003 rev.; (2) kube access is not a short-lived OIDC token, so the "no static kubeconfig secrets in CI" line in A-5 is replaced by the two-token pattern in ADR-015 (verified: Rancher mints 5-min cluster-scoped tokens; SA tokens do not pass the proxy).

**Still open:** V-1, V-2, V-3 (Phase 4 / documentation tasks); D-1, D-3, D-4, D-5, D-9 … D-12 (deferred by design); D-2 engine choice (ADR before Phase 2 schema). No `CLAUDE.md` exists yet (Phase 0 deliverable); the repository was `git init`-ed this session with docs only.

**Next prompt** (03 Appendix A, verbatim):

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
