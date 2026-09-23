# Porting CI to GitLab (ADR-015, assumption A-13)

The workflows under `.github/workflows/` contain **no logic**: every step is `make <target>`
(`tests/harness/test_ci_wrappers.py::test_ci_workflow_only_calls_make` enforces it). Porting CI is
therefore rewriting four small YAML files; the Makefile, the gates and the tests do not change.

## What exists

| Workflow | Trigger | Jobs → Make targets |
|---|---|---|
| `ci.yml` | push to `main`, pull requests | one job per gate: `lint`, `lock-check`, `type`, `test`, `db-test`, `demo`, `harness-check`, `pr-surface` (needs the PR's base SHA as `PR_BASE`), `deps-allowlist`, `secret-scan`, `helm-lint`, `terraform-validate` (after `ci-terraform`); each starts with `make ci-bootstrap` |
| `deploy-demo.yml` | manual | `image`: `make image-push` (registry token, `IMAGE_PLATFORM=linux/amd64`, digest as a job output) → `deploy`: `make deploy-demo` with an OIDC token for the cluster |
| `nightly-live-smoke.yml` | schedule | `make live-smoke` (the only job that touches the network) |
| `weekly-drills.yml` | schedule | `make ci-kind-tools local-up rollback-drill local-down` |

## GitLab equivalents

```yaml
# .gitlab-ci.yml — one job per Make target, same names as the GitHub jobs (sketch)
default:
  image: ubuntu:24.04            # or a pinned runner image with make, curl, git, libpq5
  before_script:
    - apt-get update -q && apt-get install -y -q make git curl ca-certificates libpq5
    - make ci-bootstrap && export PATH="$HOME/.local/bin:$PATH"

stages: [gates]

lint:            { stage: gates, script: [make lint] }
type:            { stage: gates, script: [make type] }
test:            { stage: gates, script: [make test] }
harness-check:   { stage: gates, script: [make harness-check] }
secret-scan:     { stage: gates, script: [make secret-scan] }
pr-surface:
  stage: gates
  rules: [{ if: $CI_MERGE_REQUEST_ID }]
  variables: { PR_BASE: $CI_MERGE_REQUEST_DIFF_BASE_SHA }
  script: [git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME", make pr-surface]
terraform-validate: { stage: gates, script: [make ci-terraform terraform-validate] }
# … lock-check, db-test, demo, deps-allowlist, helm-lint the same way

nightly-live-smoke:
  rules: [{ if: $CI_PIPELINE_SOURCE == "schedule" }]
  script: [make live-smoke]
```

| GitHub concept | GitLab | Notes |
|---|---|---|
| `pull_request` + `github.event.pull_request.base.sha` | merge-request pipelines + `CI_MERGE_REQUEST_DIFF_BASE_SHA` | `pr-surface` needs the base commit fetched |
| `$GITHUB_PATH` (used by `ci-bootstrap`) | `export PATH=…` in `before_script` | `ci-bootstrap` prints the hint when `GITHUB_PATH` is unset |
| `$GITHUB_OUTPUT` (used by `image-push`) | `artifacts: reports: dotenv:` | write `digest=…` to a dotenv file and read `IMAGE_DIGEST` in the deploy job |
| GHCR with the job token | the GitLab container registry with `CI_JOB_TOKEN` (`REGISTRY_USER=gitlab-ci-token`, `REGISTRY_TOKEN=$CI_JOB_TOKEN`) | `make image-push` takes both variables already |
| GitHub OIDC (`id-token: write`) | `id_tokens: { DEMO_OIDC: { aud: energy-platform-demo } }` | the k3s `AuthenticationConfiguration` changes issuer to `https://gitlab.com` (or your instance) and the claim rules to `project_path` and `ref`; `scripts/oidc_kube_context.sh` reads the token from the variable instead of the GitHub token endpoint |
| `schedule:` workflows | pipeline schedules | same Make targets |
| Branch protection + CODEOWNERS | protected branches, merge-request approval rules, `CODEOWNERS` (GitLab Premium for required code-owner approval) | `docs/branch-protection.md` lists the settings |
| Actions pinned to a commit SHA | `include:` components pinned by SHA, or none | `make workload-check` covers images; add a check if components are used |

Nothing in `energy_platform/`, `targets/` or the chart refers to GitHub. The GitHub-specific parts
are the OIDC issuer and claim rules in the demo's cloud-init (`authn.yaml.tftpl`, `rbac.yaml.tftpl`),
`scripts/oidc_kube_context.sh` (the Actions token endpoint), the workflow files and `CODEOWNERS`.
