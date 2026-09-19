# Progress log

One dated entry per session. Newest first.

---

## 2026-09-19 — Decisions session (no platform code)

**Verified** (`00-assumptions.md` §5; access: e-INFRA Rancher kubeconfig, MetaCentrum Cloud Brno1 application credential, CESNET S3, e-INFRA LLM; all credentials kept outside the repository):

| V | Verdict | One line |
|---|---|---|
| V-4 | CONFIRMED | Tenant only: no CRDs; CronJobs/NetworkPolicies allowed; `restricted` Pod Security enforced; ingressclass list Forbidden; Argo CRDs present but CronWorkflow create denied; CNPG, cert-manager, prometheus-operator creatable in-namespace; no External Secrets; quota 6/10 CPU, 5/9 GiB |
| V-5 | CONFIRMED | No Magnum in Brno1 catalog; quota 20 vCPU / 10 instances / 50 GB / 1 network / 1 floating IP; Ubuntu jammy+noble images |
| V-6 | CONFIRMED | S3 (Ceph RGW) versioning + object lock + lifecycle verified on store A; Swift on a separate Brno endpoint verified as store B; storage-class probe: only STANDARD exists, lifecycle accepts unknown classes silently → ADR-021 (tiering job) |
| V-7 | CONFIRMED | OpenAI-compatible endpoint, 34 models |
| V-8 | PARTIAL | Federated (Shibboleth/Perun) identity, but kubeconfig is an opaque Rancher token with 1-year TTL → CI deploy identity = namespace-scoped token secret with recorded expiry |
| V-9 | CONFIRMED | No proxy; OTE, ČEPS, ENTSO-E reachable from a pod |
| V-10 | CONFIRMED | No managed Postgres; CNPG operator pre-installed |

Register changes: A-5 cost-if-false updated; A-13 (GitHub Actions) and A-14 (`restricted` PSS) added.

**Decided** (`docs/adr/`, all ACCEPTED): ADR-001-amend (three profiles; MetaCentrum = reference environment), ADR-003-rev (CronJob + run ledger, no CRDs), ADR-014 (tooling), ADR-015 (GitHub Actions as thin wrapper over Make; A-13), ADR-016 (release and rollback), ADR-017 (manifest YAML/JSON Schema/directory convention/`secretRef`), ADR-018 (`tstzrange`, append-only versions, both timestamps), ADR-019 (five parsers, dependency allowlist), ADR-020 (Bronze fixtures, YAML goldens, Hypothesis, nightly smoke), ADR-021 (Bronze cold tier as a platform `rclone` tiering job with deploy-time probe; resolves D-8; filed after a follow-up storage-class probe the same day). `02` reconciled with superseded text kept; `03` Phases 0–3, 5, 8 and appendices reconciled; `00` §6 all ticked. No phase checkbox ticked.

**Contradictions found:** none against `00` §3. Two nuances recorded: (1) Argo is installed on the reference cluster yet unusable by a tenant, which strengthens ADR-003 rev.; (2) kube access is not a short-lived OIDC token, so the "no static kubeconfig secrets in CI" line in A-5 needs the fallback recorded in ADR-015.

**Still open:** V-1, V-2, V-3 (Phase 4 / documentation tasks); whether Rancher can mint short-lived tokens for a CI principal (V-8); D-1, D-3, D-4, D-5, D-9 … D-12 (deferred by design); D-2 engine choice (ADR before Phase 2 schema). No `CLAUDE.md` exists yet (Phase 0 deliverable); the repository was `git init`-ed this session with docs only.

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
