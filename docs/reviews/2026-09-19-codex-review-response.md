# Response to the Codex pre-coding review (2026-09-19)

| | |
|---|---|
| Reviewed snapshot | `7d872ea` (Phase 0 done, no platform code) |
| Review material | `codex-review/` (README, 01–06, evidence/) — kept verbatim, not edited |
| This document | one verdict per finding, the reasoning, and where the finding is closed |
| Plan | `docs/plans/review-1.md` |

The review's overall verdict is accepted: the repository is a design checkpoint, not a finished
submission, and the executable enforcement was thinner than the documents claimed. Nine of the
fourteen findings change something before Phase 1; the rest are scheduled into the phase that
owns them. Nothing was declined outright. Two findings are blocked on things only the author can
supply (a Git remote and the original evidence ledger).

## Verdicts

### F01 — system absent (P1) — accepted, expected

Phase 0 was scoped to the harness skeleton. No action beyond keeping README/progress honest
until Phase 8. The reviewer's point that skip-results in `helm-lint`/`terraform-validate` must
not be read as deployment passes is taken: the Makefile already distinguishes "nothing to check"
from "tool missing", and Phase 5 turns both into real gates.

### F02 — target tests not collected (P1) — accepted, demonstrated

`testpaths = ["tests"]` excluded `targets/**/tests/`. Fixed now (`testpaths` includes `targets`)
with a negative test in `tests/harness/` that plants a failing target test and asserts pytest
collects and fails it. The full "target without fixtures/goldens fails collection" rule stays a
Phase 3 deliverable (it needs the manifest model), but the collection gap no longer exists.

### F03 — egress lint incomplete (P1) — accepted, demonstrated

Five banned imports were never claimed to be a sandbox, but the documents did say "all outbound
HTTP goes through `energy_platform.fetch`" without a mechanism that made it true. ADR-027 fixes
the target capability boundary in three layers: (1) a positive file allowlist for
`targets/<id>/` and a ban on `# noqa` / `# type: ignore` inside it (`scripts/check_target_surface.py`);
(2) an extended banned-API list (`http.client`, `socket`, `ssl`, `urllib`, `subprocess`, `os.system`,
`importlib`, `ctypes`, `multiprocessing`, `asyncio` connection helpers) for everything outside
`energy_platform/fetch/`; (3) a runtime block: `tests/conftest.py` replaces `socket.socket` for
every test not marked `live`, so a parser that opens a connection fails its own test. Static lint
remains described as a guardrail; the sandbox for constrained-agent mode is ADR-007, Phase 3.

### F04 — blind test vs admission (P1) — accepted, design contradiction

Correct: 01 §10 requires a human-reviewed admission row for every new target, while Phase 7 gave
a fresh agent an unseen URL and counted any escalation as a harness defect. ADR-022 separates the
two routes. **Adapter addition** (a `dataset_id` already in the registry, host already in the host
registry) touches only `targets/<id>/`. **Source admission** (new `dataset_id`, metric, unit or
host) is a platform PR that adds the registry entries and the 01 §10 row, human-reviewed, and the
correct agent behaviour on an unadmitted source is to produce an admission request and stop.
Phase 7 now runs both routes and scores the escalation as a pass.

### F05 — version key excludes derivation (P1) — accepted, design contradiction

Correct: ADR-018's key `(observation identity, payload_sha256)` makes "same raw, fixed parser" a
no-op, which contradicts 01 §8 (parser replay must be distinguishable) and ADR-016 §4 (replay is
the repair). ADR-023 adds `derivation_id` to the version identity, separates `contract_version`
(semantic) from `parser_version` (implementation), and defines current-view selection: source
ordering basis first, derivation order second, so an old capture replayed with a new parser
never outranks a newer capture. The four proofs the reviewer asks for become Phase 2 tests.

### F06 — capture crash window, backfill vs replay, fencing (P1) — accepted

Correct on all three. ADR-024: the durable boundary is the Bronze capture-log entry, not the
ledger row; a reconciliation step lists Bronze and inserts missing ledger rows (orphan recovery);
processing attempts are their own rows; commits carry a fencing check on the lease; the gap
detector distinguishes `missing_capture` (→ backfill = a new fetch, if the source still serves the
period, else `unrecoverable`) from `unprocessed_capture` (→ replay = reprocess Bronze). "Replay
never refetches" stays true; backfill is a different verb.

### F07 — `helm test` is not an upgrade gate (P1) — accepted

Correct: a `test` hook runs only under `helm test`, outside the atomic upgrade. ADR-025: the
smoke Job is a `post-install,post-upgrade` hook (also annotated `test` for manual re-runs) so that
`helm upgrade --atomic --wait` rolls back when it fails; migrations run as `post-install,pre-upgrade`
with a lower hook weight, which also fixes the first-install ordering the reviewer flagged; the
ADR-021 storage probe joins the same hook chain. A CronJob installing "successfully" without ever
running is exactly why the hook executes one capture+process itself.

### F08 — NetworkPolicy cannot express hostnames (P1) — accepted

Correct. ADR-026 splits the promise: NetworkPolicy is a coarse, CNI-enforced boundary (default
deny; allow DNS, Postgres, object store; allow 443 to public ranges with `ipBlock.except` for
RFC 1918, link-local and the metadata address), and the per-hostname allowlist is enforced in
`energy_platform.fetch` (https only; hosts checked against the manifest **and** a human-owned
platform host registry; resolved addresses re-checked against private ranges; every redirect hop
re-validated). FQDN policies (Cilium) are optional and off in the core chart. Phase 5 must run the
local test on a CNI that enforces policy (kind's default does not).

### F09 — ownership unenforced (P1) — accepted, blocked on the remote

No remote, placeholder handle. The PR template no longer claims CI enforces every row today.
Everything else needs the Git host and is listed under "blocked on the author" below.

### F10 — secret-scan whole-line exemption (P2) — accepted, demonstrated

The exemption now applies to the matched candidate value, not the whole line: a real-looking
token next to the word "example" is reported. Scanner tests in `tests/harness/` cover the three
probes the reviewer ran (bare marker, marker plus "example" comment, marker inside an example URL)
plus the placeholders that must still pass. History scanning remains out of scope and is now
stated in the script docstring.

### F11 — frozen sync is not a lock check (P2) — accepted, demonstrated

`make lock-check` (`uv lock --check`) is part of `make check` and a CI job; the build backend is
pinned; the uv installer is pinned to a version; `actions/checkout` is pinned by commit SHA.

### F12 — evidence trail absent (P2) — accepted, open

The S01–S17 ledger cited by `docs/01-data-scope.md` is not in the repository and was not found
on this machine. Options: the author supplies `message-board/evidence/`, or Phase 4 regenerates
an index (`docs/evidence/`: request shape, observation time, digest, bounded extracted facts) with
the bounded live reads the one-week polling campaign performs anyway. Phase 4 gained that task.

### F13 — ČEPS labelling and completeness (P2) — accepted in part

Agreed that one live sample and an offset do not prove interval-start labelling. Phase 4 gained a
verification task ("confirm from the ČEPS interface description or an independent reference
before goldens are authoritative") and the mapping for T3 will carry the convention as an explicit
field per ADR-011, so a wrong guess is a one-line manifest change, not a parser rewrite. The
completeness point (NULL for "no trade" versus "not yet published") is already separated in 01 §5
by the owning-transport rule and the `pending/partial/late/complete` states; the additional fixtures
the reviewer lists are added to Phase 4.

### F14 — active documents disagree (P2) — accepted

Each row fixed in the reconciliation commit: roadmap Phase 1 field names follow ADR-018/ADR-023;
the example-manifest sentence says "five manifests (three real, two shape-only)"; D-4 default reads
`CronJob`; `00` A-3/A-5 carry dated pointers to ADR-021/ADR-015; branch-protection and pre-commit
now agree (pre-commit runs `make check` and `make deps-allowlist`); the Phase 0 allowlist checkbox
says "dev packages only; runtime names approved in ADR-019 are added when Phase 2 locks them".

## Points taken without a finding number

- "The evaluator cannot be asked" (00 purpose, A-13, ADR-015) is reworded as a choice: the brief
  invites questions; the author chose a reference environment and bounded the cost of being wrong
  instead of blocking on an answer. Same decisions, honest premise.
- Breadth (three profiles, five parsers, MCP, triage pipeline) stays in the roadmap but Phase 2's
  definition of done is the narrow complete path the reviewer describes; optional items are
  explicitly behind flags and later phases.

## Blocked on the author

| Item | Needed |
|---|---|
| F09 | a Git remote and a real maintainer handle for `CODEOWNERS`; then apply `docs/branch-protection.md` and test a rejected push |
| F12 | the original `message-board/evidence/` directory for the energy task, or agreement that Phase 4 regenerates it |

## Not changed, and why

- `docs/01-data-scope.md` is untouched (frozen; F13 is carried as a verification task, not an edit).
- `codex-review/` is untouched and stays in the repository as review evidence.
