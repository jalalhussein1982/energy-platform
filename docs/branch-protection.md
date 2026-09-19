# Branch protection (to configure on the Git host; ADR-006, ADR-015)

Settings for `main`, to apply once a remote exists. They are the mechanical half of the agent
authority model; CODEOWNERS is the other half.

| Setting | Value | Why |
|---|---|---|
| Require a pull request before merging | on, 1 approval | no direct pushes to `main` for anyone, agent or human |
| Require review from Code Owners | on | `energy_platform/`, `deployment/`, ADRs, allowlist and CI need a human owner |
| Dismiss stale approvals on new commits | on | an agent cannot append to an approved PR |
| Require status checks | `lint`, `type`, `test`, `deps-allowlist`, `secret-scan`, `helm-lint`, `terraform-validate` | the `make` targets, one job each (ADR-015) |
| Require branches to be up to date | on | gates run on the merge result |
| Require conversation resolution | on | — |
| Require signed commits | recommended | provenance for the supply-chain threat model (ADR-008) |
| Restrict who can push | maintainers only | Level 3 "merge to main" is forbidden to agents (ADR-006) |
| Allow force pushes / deletions | off | — |

Deploy identities (Phase 5) are repository secrets that no agent session can read: the CI job
mints a short-lived token from them (ADR-015 two-token pattern) and never writes it to a log.

Until a remote exists this file is the record; nothing here is enforced locally except `make check`
via pre-commit.
