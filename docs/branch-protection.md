# Branch protection (to configure on the Git host; ADR-006, ADR-015)

Settings for `main`, to apply once a remote exists. They are the mechanical half of the agent
authority model; CODEOWNERS is the other half.

| Setting | Value | Why |
|---|---|---|
| Require a pull request before merging | on, 1 approval | no direct pushes to `main` for anyone, agent or human |
| Require review from Code Owners | on | `energy_platform/`, `deployment/`, ADRs, allowlist and CI need a human owner |
| Dismiss stale approvals on new commits | on | an agent cannot append to an approved PR |
| Require status checks | `lint`, `lock-check`, `type`, `test`, `db-test`, `demo`, `harness-check`, `pr-surface`, `deps-allowlist`, `secret-scan`, `helm-lint`, `terraform-validate` | the `make` targets, one job each (ADR-015); `harness-check` and `pr-surface` are the Phase 3 gates of `docs/05-constraint-matrix.md` §2 |
| Require branches to be up to date | on | gates run on the merge result |
| Require conversation resolution | on | — |
| Require signed commits | recommended | provenance for the supply-chain threat model (ADR-008) |
| Restrict who can push | maintainers only | Level 3 "merge to main" is forbidden to agents (ADR-006) |
| Allow force pushes / deletions | off | — |

Deploy identities (Phase 5) are repository secrets that no agent session can read: the CI job
mints a short-lived token from them (ADR-015 two-token pattern) and never writes it to a log.

**Enforced since 2026-09-23** on `github.com/jalalhussein1982/energy-platform` (public): pull
request required, 1 approval, code-owner review, stale approvals dismissed, the 12 status
checks above, branches up to date, conversation resolution, no force pushes or deletion. The
author chose option (a): administrators may bypass, and GitHub records every bypass (a single
maintainer cannot approve their own PR). Signed commits and push restrictions are not set (push
restrictions exist only for organisation repositories). An agent session that uses the owner's
`gh` login is technically an administrator: for it the Level 3 rule is procedural, not
mechanical (`docs/threat-model.md` §13).

Before the remote existed this file was the record and nothing here was enforced. Locally,
`uv run pre-commit install` (not automatic) gives the laptop the same three gates as CI: `make check`,
`make deps-allowlist`, `make secret-scan`. Ownership, protected `main` and the target-only path
boundary become real only on the Git host. *(2026-09-23: `CODEOWNERS` names `@jalalhussein1982`, review F09 closed; protection enforced as above.)*
