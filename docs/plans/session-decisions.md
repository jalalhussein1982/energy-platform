# Plan — Decisions session (2026-09-19)

| | |
|---|---|
| Scope | Decisions only: verify assumptions (00 §4), accept proposed ADRs (00 §3), resolve blocking open items (02 §4.1), reconcile 02/03 (00 §6). **No platform code.** |
| Authority | 02 §2 frozen except where 00 §3 proposes a revision. 00 §3 proposals accepted at end of session unless verification contradicts them (then stop and report). |
| Touch surface | `docs/` and `docs/adr/` only. No credentials written anywhere in the repository. |
| Session protocol | 03 §0 applies: plan first (this file), one task one commit, progress log at the end. `make check` does not exist yet (Phase 0 not started) and is not a gate for docs-only commits. |

## Pre-flight findings

- Repository is **not yet a git repository** (`.git/` absent). Task 5 requires commits → `git init` needed; asked for in the single start-of-session question.
- No `CLAUDE.md`, no `docs/progress.md`, no `docs/adr/`, no `docs/plans/` existed at session start. `docs/adr/` and `docs/plans/` are created by this plan; `docs/progress.md` by Task 5.
- Local tooling: `git`, `ssh`, `kubectl`, `aws`, `curl`, `jq` present. `helm`, `openstack`, `rclone`, `mc`, `s3cmd` **missing** locally → V-5 (`openstack`), V-6 (`rclone`), V-10 (`helm search repo`) run over SSH on the MetaCentrum front-end if the tools exist there; otherwise PARTIAL with the missing tool named.
- Candidate access already on this machine: kubeconfig `~/.kube/sahel-cerit.yaml` (Rancher-proxied cluster at `rancher.cloud.e-infra.cz`, namespace `hussein-ns`) and SSH alias `skirit` (MetaCentrum front-end). To be confirmed by the user before use.

## Ordered tasks

### T1 — Verification over live access (00 §4, V-4 … V-10)

| Step | Action | Acceptance check |
|---|---|---|
| 1.0 | Ask once for: SSH alias, kubeconfig path + namespace, OpenStack RC file, S3 endpoints/credentials (two stores), LLM endpoint/token, and permission to `git init`. | Question asked once; answers used only as env vars / file paths in the shell, never written to the repo. |
| 1.1 | V-4: `kubectl auth can-i create customresourcedefinitions…`, `can-i create cronjobs -n $NS`, `can-i create networkpolicies -n $NS`, `api-resources | grep -Ei 'argoproj|cnpg|external-secrets|monitoring.coreos|cert-manager'`, `get ingressclass`, `get storageclass`, `get clusterissuer`, `get resourcequota,limitrange -n $NS -o yaml`. | Every command run (≤ 3 attempts); Forbidden/not-found recorded verbatim; verdict for A-1, A-8, A-10 written. |
| 1.2 | V-5: `openstack catalog list`, `coe cluster template list`, `quota show`, `flavor list`, `image list | grep -i ubuntu` using the RC file (locally if `openstack` installable via `uvx`/`pipx` without touching the repo, else over SSH). | Verdict for A-2 / D-1; Magnum presence stated from `catalog list` and `coe` output. |
| 1.3 | V-6: `list-buckets`, `get-bucket-versioning`, `put-object-lock-configuration` on a scratch bucket `energy-platform-verify-20260919`, `get-bucket-lifecycle-configuration`, Swift `object store account show`, `rclone lsd` for both endpoints. Scratch bucket/object deleted afterwards. | Verdict for A-3 (S3 API, versioning, object lock, lifecycle, second independent endpoint). Scratch resources gone at end (listed to prove it). |
| 1.4 | V-7: `curl $LLM_BASE_URL/v1/models` with bearer token from env. | Verdict for A-4; model list excerpt (trimmed) recorded, token never echoed. |
| 1.5 | V-8: `kubectl config view --minify`; inspect user block for exec/OIDC; note token TTL if discoverable (decode JWT `exp` claim without printing the token). | Verdict for A-5; token type and TTL recorded. |
| 1.6 | V-9: one pod `energy-platform-verify-20260919` (`curlimages/curl`, `--rm`) printing proxy env vars and HTTP codes for OTE, ČEPS, ENTSO-E. Pod removed afterwards. | Verdict for A-7 and A-12; pod absent at end. |
| 1.7 | V-10: `helm search repo` on any configured repos (over SSH if `helm` exists there); `kubectl get` on Rancher catalog CRs if readable (`catalog.cattle.io` / `apps.cattle.io`); e-INFRA docs as secondary only. | Verdict for A-11; which Postgres mode the `tenant` profile uses on the reference cluster. |
| 1.8 | Append one line per V-item to 00 §5 in the required format; update 00 §2 "Survives A/B/C" / "Cost if false" only where a result changes them, with the reason in §5. | §5 has exactly seven new lines (V-4 … V-10); every unrun or blocked step is PARTIAL with "what would resolve it". |

### T2 — Accept proposed ADRs

| Step | Action | Acceptance check |
|---|---|---|
| 2.1 | `docs/adr/ADR-template.md` with sections Status / Context / Decision / Rationale / Rejected / Consequences / Verification refs. | File exists; every ADR filed this session follows it. |
| 2.2 | `ADR-003-rev-orchestration-without-crds.md` — ACCEPTED, cites V-4. If V-4 shows CRD creation is allowed, note it and keep the tenant requirement (A-1 rationale: ČEZ's cluster is what matters). | Status ACCEPTED; V-4 line quoted; Argo rejection rationale preserved. |
| 2.3 | `ADR-016-release-and-rollback.md` — ACCEPTED, from 00 §3. | All six decision points present; verification refs to V-4 (CronJob rights) and V-6 (Bronze immutability for replay). |
| 2.4 | `ADR-001-amend-three-profiles.md` — ACCEPTED, from 00 §2.1. | Three-profile table present; "reference environment, not production" wording present. |

### T3 — Resolve blocking open items (02 §4.1)

| Step | Action | Acceptance check |
|---|---|---|
| 3.1 | B-1 → `ADR-017-manifest-format-and-registration.md` (YAML; versioned JSON Schema; directory convention; `secretRef`). | One short ADR per B-item, each citing 02 §4.1 default and any V-result that caused deviation. |
| 3.2 | B-2 → `ADR-018-canonical-schema-details.md` (`tstzrange`; append-only versions + current view; store both timestamps). | as above |
| 3.3 | B-3 → `ADR-019-generic-parsers-and-allowlist.md` (five parsers; `lxml`, `openpyxl`, `pydantic` v2). | as above |
| 3.4 | B-4 → `ADR-014-tooling-baseline.md` (Python 3.12, `uv`, `ruff`, `mypy --strict`, `import-linter`, `pre-commit`, CODEOWNERS). Numbered 014 because 03 Phase 0 already names it. | as above |
| 3.5 | B-5 → `ADR-015-ci-platform.md` (GitHub Actions; workflows are thin wrappers over Make targets). Add **A-13** to 00 §2 with cost-if-false "port to GitLab CI". Numbered 015 because 03 Phase 0 already names it. | ADR filed; A-13 row present in 00 §2. |
| 3.6 | B-6 → `ADR-020-test-strategy.md` (Bronze objects as fixtures; YAML goldens; Hypothesis for DST; nightly live smoke). | as above |
| 3.7 | D-2, D-6, D-7 per 00 §6 (changed) and new D-13 (canary, optional) — recorded in 02 §4.2 text (Task 4), not as separate ADRs; D-2 keeps "ADR before schema" in 03 Phase 2. Other D-items untouched. | 02 §4.2 rows D-2, D-6, D-7 updated; D-13 row added; D-1, D-3 … D-12 unchanged. |

### T4 — Reconcile 02 and 03 (00 §6)

| Step | Action | Acceptance check |
|---|---|---|
| 4.1 | 02 ADR-001: three-profile table; MetaCentrum/e-INFRA as reference environment. Old text kept under a "Superseded by ADR-001-amend on 2026-09-19" note. | Checklist item ticked in 00 §6. |
| 4.2 | 02 ADR-003: body replaced by ADR-003 rev.; Argo rejection rationale kept; superseded note. | ticked |
| 4.3 | 02 ADR-004: replay and gap detector reference the run ledger. | ticked |
| 4.4 | 02 §4: D-2, D-6, D-7 reworded; D-13 added; B-1 … B-6 marked resolved with ADR refs. | ticked |
| 4.5 | 02 §2: ADR-016 appended. | ticked |
| 4.6 | 02 §4.3: V-4 … V-10 rows pointing to 00. | ticked |
| 4.7 | 03 Phase 2: `ledger/` module + ledger migrations; "downgrade script per migration" in DoD. No checkbox ticked. | ticked in 00 §6; all Phase checkboxes remain `[ ]`. |
| 4.8 | 03 Phase 3: four new constraint-matrix rows. | ticked |
| 4.9 | 03 Phase 5: remove Argo CronWorkflow; add CronJob template, run ledger, `helm test` hook, rollback drill, tenant-profile deploy to reference cluster. | ticked |
| 4.10 | 03 Phase 8: README section "Assumptions and what they cost". | ticked |
| 4.11 | Consistency sweep: 03 Phase 0 starter prompt (ADR-014/015 now exist), Phase 2 "No Argo" wording, Appendix A/B mentions of Argo/ESO. | `grep -n -i argo docs/03-roadmap.md` shows only historical/superseded mentions. |

### T5 — Close the session

| Step | Action | Acceptance check |
|---|---|---|
| 5.1 | `docs/progress.md`: date; verdict per V; ADR list; what remains open; exact next prompt (03 Appendix A, "Begin Phase 0"). | File exists with those four parts. |
| 5.2 | `git init` (if permitted) and small conventional commits: `docs(plans)`, `docs(assumptions): verification log`, `docs(adr): …`, `docs(02): reconcile …`, `docs(03): reconcile …`, `docs(progress)`. | `git log --oneline` shows ≥ 5 commits, each touching only `docs/`. |
| 5.3 | Final message: table of V-items with verdicts; ADRs filed; contradictions found; what is needed before Phase 0. | — |

## Stop conditions

- A verification result contradicts a 00 §3 proposal → stop, report, do not improvise.
- A task needs a decision only the user can make → stop at that task, ask one precise question.
- Any step would write a credential into the repository → refuse the step, mark PARTIAL.
