# ADR-015 — CI platform: GitHub Actions as a thin wrapper over Make

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-5 (`02-architecture-decisions.md` §4.1); registers A-13 in `00-assumptions.md` §2 |

## Context

The brief allows questions, but which Git host ČEZ runs is not worth blocking delivery on: the assignment is delivered as a Git repository, GitHub Actions is the default for a take-home, and the cost of being wrong must be bounded. *(2026-09-19: premise reworded after review; was "we cannot ask". Decision unchanged.)*

## Decision

- CI runs on **GitHub Actions**.
- **CI workflow files are thin wrappers that only call Make targets.** No logic, no shell beyond `make <target>`, no tool installation that is not itself a Make target (`make ci-bootstrap`). All logic lives in the `Makefile`, so porting to GitLab CI (or anything else) is mechanical: rewrite the wrapper YAML only.
- Required jobs (each one Make target): `lint`, `type`, `test`, `deps-allowlist`, `secret-scan`, `helm-lint` (renders the chart with `tenant` values and lints against the `restricted` Pod Security profile, A-14), `terraform-validate`, `terraform-test`.
- Deploy identity is **never** an agent-held credential (ADR-006). On a Rancher-fronted tenant cluster (the reference cluster) it is the **two-token pattern** (V-8, second pass): one long-lived, **cluster-scoped** Rancher API token is the CI secret (expiry recorded in the secret's metadata; a scheduled job alerts 30 days before; bounded by the Rancher `auth-token-max-ttl` setting); each deploy job first calls the Rancher token API to mint a **≤ 5-minute cluster-scoped token** and uses only that for `helm`/`kubectl`. The long-lived token never reaches a kubeconfig. Rancher cannot create a separate CI principal for a tenant, and Kubernetes ServiceAccount tokens are rejected by the Rancher proxy, so this is the least-privilege shape available there. Wherever the target cluster accepts workload-identity federation (hyperscaler managed Kubernetes, or a cluster we control with structured authentication), federation replaces the long-lived token and the Make target is unchanged.

## Rationale

Bounded cost if false (A-13: "port to GitLab CI"); identical commands on laptop and CI; no vendor-specific logic to audit.

## Rejected

GitLab CI now (equal effort, no evidence ČEZ uses it); Jenkins (no); Dagger/Earthly (extra tool to explain).

## Consequences

`00` §2 gains row A-13. 03 Phase 0 "CI skeleton (platform per B-5)" now reads "GitHub Actions wrappers over Make". A `docs/ci-porting.md` stub is a Phase 8 item.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-8 · CONFIRMED (opaque Rancher token, 1-year TTL; short-lived cluster-scoped tokens mintable from it; SA tokens rejected by the proxy) — shapes the deploy-identity clause.
