# ADR-001 (amendment) — Three deployment profiles; MetaCentrum/e-INFRA is the reference environment

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | amends ADR-001 (`02-architecture-decisions.md` §2); source `00-assumptions.md` §2.1 |
| Supersedes | the "two reproducibility profiles" paragraph and directory tree of ADR-001 |
| Amended by | ADR-028 (2026-09-19): rule 4 gains "no scheduled workload, release or bucket on the reference environment"; rule 5's "first real environment" is the demo cluster (Hetzner), not the reference cluster; `own-cluster` gains a second Terraform root (`hcloud`) |

## Context

ADR-001 defined two profiles (`local`, `openstack`). The assumptions register (A-1, A-8, A-10, A-11, A-14) shows that the most likely ČEZ environment is a *shared* cluster where we hold a namespace only: no CRDs, no cluster services of our own, quota-enforced, `restricted` Pod Security. Neither existing profile describes that case. V-4 confirmed every one of those constraints on the reference cluster.

## Decision

Kubernetes remains the deployment contract, Helm defines workloads, Terraform provisions infrastructure only. There are **three** profiles:

| Profile | Where | Cluster-level capability | Postgres | Secrets | Metrics |
|---|---|---|---|---|---|
| `local` | kind on a laptop | We install everything (ingress-nginx, cert-manager, MinIO×2) | `statefulset` | SOPS-decrypted `Secret` | `/metrics` + annotations |
| `tenant` | Any shared cluster (reference: e-INFRA Rancher; scenario A) | **None** — consume by name (`ingressClassName`, `clusterIssuer`, `storageClassName`) | `statefulset` or `external`; `cnpg` allowed only when the operator is already present (it is on the reference cluster, V-4/V-10) | plain `Secret` from CI/SOPS | `/metrics` + annotations; `PodMonitor` allowed behind flag when prometheus-operator is present |
| `own-cluster` | Terraform on OpenStack (reference: MetaCentrum Cloud; scenario B/C) | Operators allowed behind values flags | `cnpg` | ESO behind `secrets.eso.enabled` | `PodMonitor` behind `metrics.operator.enabled` |

```text
deployment/
├── local/            # kind + Helm, driven by Make. No Terraform.
├── tenant/           # values only: values-tenant.yaml + values-<env>.yaml; no Terraform
├── own-cluster/      # Terraform provisions (network/, nodes/, storage/); Helm deploys
│   ├── terraform/
│   └── values-own-cluster.yaml
└── helm/energy-platform/
```

Rules:
1. **Platform code is identical across profiles.** Only Helm values and Terraform differ.
2. **Anything cluster-level appears only in `own-cluster`, behind a flag, never in the core chart.** The core chart must render and install with `tenant` values on a namespace that forbids CRDs.
3. **Every pod in the core chart is `restricted`-PSS-clean** (A-14): `runAsNonRoot`, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, requests and limits set. CI renders the chart and lints it against the restricted profile.
4. **MetaCentrum / e-INFRA CZ is the reference environment**: the assumption base from which constraints are derived and against which the `tenant` profile is first deployed. It is not the production platform and must not be named as such in any submitted document (academic terms, best-effort SLA, not reproducible by the evaluator).
5. `tenant` is the first real environment (03 Phase 5); `own-cluster` is proven by `terraform validate` and `terraform test` with mock providers in CI.

## Rationale

A tenant chart runs in all three scenarios (A, B, C) unchanged; a chart that needs cluster rights runs only in B and C. Making `tenant` the core and everything else an additive flag is the cheapest robust choice, and it is strictly more portable. The reference-environment wording keeps the sovereignty argument honest: portability plus a residency policy, not a vendor or an academic cloud.

## Rejected

- Two profiles with `openstack` doing double duty (mixes cluster-building with tenant deployment; hides A-1).
- A separate chart per profile (three charts = three drifts).
- Naming MetaCentrum as production (see ADR-001 original rejection; unchanged).

## Consequences

- `02` ADR-001 text replaced (original kept under a superseded note).
- `03` Phase 5 gains "tenant profile deploy to the reference cluster as the first real environment"; Phase 3 constraint matrix gains "workload without resource requests".
- D-2, D-6, D-7 become value-driven contracts (`postgres.mode`, `metrics.operator.enabled`, `secrets.eso.enabled`); see `02` §4.2.
- Devil's advocate: a `restricted`-clean chart forbids privileged sidecars (e.g. some CSI or mesh injectors). Compensation: none needed for this platform; nothing in it requires privilege.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-4 · CONFIRMED (no CRDs, quotas, PSS restricted, ingressclass Forbidden, operators pre-installed); 2026-09-19 · V-10 · CONFIRMED (no managed Postgres, CNPG operator present).
