# 10 — What has been tested, and where the record is

| | |
|---|---|
| Status | Record, v1.0 (2026-09-26). Describes the repository at `f5ef43a`; the demo runs Helm revision 29 of `327e45e`. |
| Purpose | One page that lists every kind of test the platform has been put through, with the document that holds the evidence. Companion: `docs/11-misbehaviour-test-plan.md`, the tests **not yet** run, written for the next engineer. |
| Rule | Nothing here is claimed without a section to read. A row without a reference is a defect of this page. |

## 0. The shape of the testing

Five layers, from the cheapest to the most expensive:

1. **Automated gates** on every commit and in CI: lint, types, offline tests with sockets disabled, the harness checks, the surface classification of a diff, the allowlist, the secret scan, the Helm lint under the restricted profile, Terraform validation (§1).
2. **Negative tests**, one per named constraint: the 77 rows of `docs/05-constraint-matrix.md`, each with a test that proves the gate refuses the failure mode (§2).
3. **Blind acceptance runs**: a fresh agent or a junior, given only the contributor page and a source, must produce a target PR that passes CI and touches nothing else (§3).
4. **Verification of assumptions and sources**: the infrastructure claims of `docs/00-assumptions.md` §5 and the bounded live reads behind every fixture (§4, §5).
5. **Operational drills on a running cluster**: restore, rollback, alert delivery, the clean-clone gate, egress enforcement, the deploy identity's limits, the public exposure (§6, §7).

External reviews (§8) cut across all five. §9 states what has **not** been tested.

## 1. Automated gates

`make check` = `lint` + `lock-check` + `type` + `test` + `harness-check`, green before every commit (`docs/03-roadmap.md` §0). CI runs twelve jobs, one per gate, no logic in the workflow (ADR-015), and branch protection requires all twelve plus one approving review from a code owner (`docs/branch-protection.md`):

| CI job | What it proves |
|---|---|
| `lint` | ruff, ruff format, import-linter (layer boundaries: `httpx` only under `fetch/`), the target surface check |
| `lock-check` | the lockfile matches `pyproject.toml`; no unlocked dependency |
| `type` | static types |
| `test` | 960 offline tests, sockets disabled; `live`-marked tests never run in CI |
| `db-test` | 36 tests against an ephemeral PostgreSQL (migrations up **and down**, ledger, silver) |
| `demo` | the end-to-end demo path on fixtures |
| `harness-check` | `validate-targets` + `migration-check` + `workload-check` |
| `pr-surface` | the diff is classified: a target PR touches `targets/<id>/` only |
| `deps-allowlist` | every dependency has an allowlist entry and an ADR |
| `secret-scan` | no credential in the tree |
| `helm-lint` | `helm lint` + template of tenant, local and all-flags values → digests, resources, restricted Pod Security |
| `terraform-validate` | `tofu validate` + the `plan.tftest.hcl` sizing-and-controls test (issuer, audience, claim rules, anonymous off, API CIDRs) |

The 960 offline tests by area, at `f5ef43a`: contracts 145, harness 208, fetch 95, runtime 85, bronze 37, store 32, mapping 29, parse 25, cli 18, triage 12, live 1 (never in CI). 35 are skipped offline by design (live or platform-conditional).

## 2. Negative tests — the constraint matrix

`docs/05-constraint-matrix.md` has 77 rows, C-01 to C-77: failure mode → gate → the test that proves the gate. Every negative test sits next to a positive control. The classes, with the message a contributor sees (`docs/08-adding-a-target.md` §12):

| Misbehaviour proven refused | Gate | Message |
|---|---|---|
| fetch or normalise code in a target; a hardcoded URL; an import in a target `.py` | surface check | `hardcoded URL`, `float()`, `import …` |
| `float()` on a raw Czech number | validator | `float()` |
| a naive datetime; 96 slots assumed on a DST day | contract + DST goldens | golden `value … expected …` |
| a unit invented, a metric renamed, an unadmitted host or dataset | registry / admission | `unit … must be the registry unit`, `ADMISSION_REQUIRED` |
| a source read by column position | validator (C-04) | `positional access` |
| a `REPLACE_ME`, `TODO`, `FIXME` left | placeholder check (C-13) | `placeholder left in the target` |
| a missing fixture, a golden pointing nowhere | validator (C-14, C-15) | `no fixture` / `fixture … does not exist` |
| a file outside `targets/<id>/`; a registry edit in a target PR | `pr-surface` | `not a target PR` |
| a new dependency | `deps-allowlist`, `lock-check` | needs an ADR and an allowlist entry |
| a unit test that reaches the network | sockets disabled | error at the socket, laptop and CI alike |
| a credential in the tree; a `secretRef` naming a platform credential | `secret-scan`, validator | red before a human reads it |
| a `:latest` image, an unpinned Action, a pod without limits, a migration without a downgrade | workload check, migration check, Helm lint | named tests under `tests/harness/` |
| a `noqa` or a skip added to get green | suppression check on the diff | it is a constraint |
| a credential typed into the Alertmanager receiver values; a route to an undeclared receiver | render refusals C-76, C-77 | refused by `helm template`, by name, value not echoed |
| an MCP write outside the surface, a read of `.git` or a secret, `open_pr` with a red gate | MCP tool guards (C-47…C-53) | `tests/harness/test_mcp.py` |
| a pod created before its NetworkPolicy applies (kube-router's asynchronous apply) | policy gate C-65 | the pod waits for its policy |

## 3. Blind acceptance runs (`docs/09-acceptance-report.md`)

| Run | Profile | Result |
|---|---|---|
| 1 | fresh agent, Route A, a pre-admitted OTE source | PR #1: `targets/ote_imbalance_settlement/` only, CI 12/12, 45/45 golden rows re-derived by hand |
| 2 | fresh agent, an **unadmitted** source (Open-Meteo) | PR #2: the admission request only; the non-commercial terms flagged |
| 3 | the junior path, CLI only, `docs/08` followed literally | PR #3: target only, CI 12/12, 32/32 golden rows re-derived |
| 4 | strictly blind (Phase 9: no memory, no connectors), source version 2 | PR: target only, CI green; two documentation defects found and closed |

Criterion: no core change, no architectural guidance, no question answered. **4 of 4 pass.**

## 4. Verification of assumptions (`docs/00-assumptions.md` §5)

V-4 to V-14 were run with real credentials on 2026-09-19 and later, verdicts in the table: tenant rights and CRD limits (V-4), OpenStack services and quotas (V-5), S3 endpoints and lifecycle (V-6), the inference endpoint (V-7), OIDC-issued kube access (V-8), pod egress (V-9), managed Postgres (V-10), **egress NetworkPolicy enforced by the CNI** (V-11), Hetzner Object Storage with Object Lock (V-12), OCI Object Storage with a retention rule (V-13), k3s structured authentication trusting the GitHub Actions issuer (V-14). V-1 to V-3 were documentation and harness tasks, closed in Phase 4 and `docs/06`.

## 5. Source verification and fixtures (`docs/06-source-verification.md`, `docs/evidence/`)

- **19 bounded live reads** on 2026-09-20 (WSDLs, terms, robots, one SOAP and one XLSX payload per target, the DST days 2026-03-29 and 2025-10-26, the 2024-06-30 resolution change), each with method, status, size and SHA-256 in `docs/evidence/README.md`; raw payloads kept outside the repository.
- **Synthetic fixtures** copy the shape of those reads. OTE answered on 2026-09-24 that its data is for internal use only, so no captured payload is committed and no dashboard is public.
- **DST**: every target ships a spring (92-slot) and an autumn (100-slot) fixture; the goldens for both days are re-derived by hand in every blind run.
- **ČEPS load**: the two series are equal on every quarter-hour and hourly item and differ on the daily aggregate; both stored as published, the question sent to ČEPS on 2026-09-24, follow-up due around 2026-10-02 (`docs/06` §4.2).

## 6. Operational drills (`docs/07-operations.md`)

| Drill | When | Result | Section |
|---|---|---|---|
| Restore from store B on kind | 2026-09-22 | base + WAL fetched from the replica, ledger rebuilt, two targets byte-identical; RTO figures recorded | §5.1 |
| Bounded backup footprint | 2026-09-23 | retention and size bounded (ADR-036 amendment 1) | §5.2 |
| Drill memory does not grow with the table | 2026-09-24 | measured | §5.3 |
| Scheduled restore drill on the demo | 2026-09-24, 2026-09-25 | both nightly runs **failed** (memory; then a timing defect of the new comparison), each fixed the same day; manual two-phase runs succeeded, the last at revision 28 with every version of every target reproduced (718.6 s restored, 1 923.2 s Bronze-only) | §5.4 |
| Rollback drill on kind | 2026-09-22 | a failing smoke hook rolls the release back; values and schema restored | §6 |
| Alert delivery drill | 2026-09-25 kind and demo | `firing` and `resolved` delivered to the platform receiver; ~3.5 min from failure to delivery | §7.2 |
| Alert channel drill into a mailbox | 2026-09-26 demo | `firing` and `resolved` in the log and in the operator's inbox in the same second; under three minutes from the failure; notifier log clean | §7.3 |
| Clean-clone gate | 2026-09-23 (twice), 2026-09-24, 2026-09-25 | pass on a machine that had never seen the repository; the MinIO withdrawal of 2026-09-24 broke it for a day and RustFS replaced it | §8.1–8.4 |
| Local egress test (ADR-026 layer 1) | with every `make local-up` | capture pod reaches OTE; capture pod to the metadata service and a private address **blocked**; process pod to the internet **blocked** | `deployment/local/egress-test-job.yaml` |
| Smoke test | with every `make local-up` and as the Helm test hook | one gaps-and-freshness run, the freshness metric present, a restore-drill dry run | `make smoke-test` |
| Incident: T2 backfills stored today's file | 2026-09-23 | found on the demo, fixed with tests, 113 wrong captures recorded as invalidations | §4.3 |
| The OIDC identity may not manage Roles | 2026-09-25 | a push failed Helm's pre-flight and changed nothing; the objects are now gated and admin-applied | §4.4 |
| Nightly live smoke | nightly | the `nightly-live-smoke` workflow, green on `d5fa9ce` | `.github/workflows/` |

## 7. Identity and exposure probes

- **Deploy identity** (`docs/07` §4.2, 2026-09-23): an ID-token-only kubeconfig gets namespace verbs and is **Forbidden** on cluster verbs; a token from another branch gets **401**.
- **Public exposure** (2026-09-26, from a non-admin address, both nodes): only `6443/tcp` answers on the server, nothing on the agent; port 443 is passed by the firewall and nothing listens; ping dropped; SSH filtered. Every anonymous API path returns **401**, version and health included (anonymous authentication is off). The only pre-authentication disclosure is the TLS certificate: a k3s server named `energy-platform-demo-server` with the private addresses `10.10.1.10` and `10.43.0.1`. The API is world-reachable on purpose (GitHub runners have no fixed addresses; ADR-035 §4, threat model §14). Finding: the firewall's admin address is a fixed `/32` and no longer matches the author's current network.
- **Node metadata service**: blocked from pods by NetworkPolicy (the local egress test); the node-level block is prepared and not yet applied on the demo (`deployment/own-cluster/README.md`).

## 8. External reviews (`docs/reviews/`)

| Review | Snapshot | Answered |
|---|---|---|
| Codex pre-coding review, 2026-09-19 | `7d872ea` (Phase 0, no code) | one verdict per finding, plan `docs/plans/review-1.md` |
| Codex review 2, 2026-09-24 | 17 findings | closed by Phase 10 |
| Codex review 3, 2026-09-25 | 6 findings + a final-report assessment | 5 closed with tests or a drill, 1 stated as a boundary (ADR-028 amendment 1); Phase 13 |

## 9. Not tested — the honest boundary

- **Failover / node loss.** One server in the Terraform module, embedded etcd needs three, CNPG without a backup chain refuses the drill; a decision, not a drill (ADR-028 amendment 1, the final report).
- **A live DST day** end to end on the demo (the fixtures cover it; the cluster has not lived through one).
- **The month boundary**: the monthly targets' first scheduled run is 2026-10-01.
- **k3s certificate expiry** (one year), **Object Lock expiry** (90 days), **restore from a tampered backup**.
- **An adversarial or careless contributor.** The blind runs prove the happy path; no run has yet tried to break the gates on purpose. That is `docs/11-misbehaviour-test-plan.md`.
