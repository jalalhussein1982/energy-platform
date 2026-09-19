# ADR-015 — CI platform: GitHub Actions as a thin wrapper over Make

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-5 (`02-architecture-decisions.md` §4.1); registers A-13 in `00-assumptions.md` §2 |

## Context

We cannot ask ČEZ whether they run GitHub or GitLab. The assignment is delivered as a Git repository; GitHub Actions is the default for a take-home. The cost of being wrong must be bounded.

## Decision

- CI runs on **GitHub Actions**.
- **CI workflow files are thin wrappers that only call Make targets.** No logic, no shell beyond `make <target>`, no tool installation that is not itself a Make target (`make ci-bootstrap`). All logic lives in the `Makefile`, so porting to GitLab CI (or anything else) is mechanical: rewrite the wrapper YAML only.
- Required jobs (each one Make target): `lint`, `type`, `test`, `deps-allowlist`, `secret-scan`, `helm-lint` (renders the chart with `tenant` values and lints against the `restricted` Pod Security profile, A-14), `terraform-validate`, `terraform-test`.
- Deploy identity is **never** an agent-held credential (ADR-006). On the reference cluster it is a namespace-scoped Rancher API token stored as a CI secret with a recorded expiry (V-8); federation (OIDC workload identity) is used wherever the target cluster supports it.

## Rationale

Bounded cost if false (A-13: "port to GitLab CI"); identical commands on laptop and CI; no vendor-specific logic to audit.

## Rejected

GitLab CI now (equal effort, no evidence ČEZ uses it); Jenkins (no); Dagger/Earthly (extra tool to explain).

## Consequences

`00` §2 gains row A-13. 03 Phase 0 "CI skeleton (platform per B-5)" now reads "GitHub Actions wrappers over Make". A `docs/ci-porting.md` stub is a Phase 8 item.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-8 · PARTIAL (kubeconfig credential is an opaque Rancher token, 1-year TTL) — shapes the deploy-identity clause.
