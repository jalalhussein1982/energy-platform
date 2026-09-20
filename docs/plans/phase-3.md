# Plan — Phase 3: Harness (2026-09-20)

> **For agentic workers:** execute task by task. One task = one commit, `make check` green before
> each commit (03 §0). Steps use `- [ ]` checkboxes.

| | |
|---|---|
| Goal | Make the wrong thing impossible for a junior and an agent. Gate: every row of `docs/05-constraint-matrix.md` has a mechanical gate and a negative test, and every negative test is rejected by its mapped gate. |
| Spec | `docs/03-roadmap.md` Phase 3; `docs/02-architecture-decisions.md` ADR-005…ADR-008; `docs/adr/` ADR-006, ADR-007, ADR-014, ADR-016, ADR-020, ADR-022, ADR-026, ADR-027; `docs/04-contracts.md` §3.7, §3.8; `docs/05-constraint-matrix.md` (written first, Task 3.1). |
| Architecture | `energy_platform/harness/` — the library behind the scaffolder, the surface check, the golden runner, PR surface classification and the admission request; `energy_platform/mcp/` — a stdio JSON-RPC server exposing the ADR-007 tools as thin wrappers over `harness`; `energyctl` gains `new-target`, `validate <id>`, `record-fixture`, `run-target-tests`, `admission-request`, `pr-bundle`, `mcp-serve`. Scripts stay thin (`scripts/check_*.py` call the library; git and subprocess only in `scripts/` and `tests/harness/`). |
| Tech | No new dependency. The MCP transport is JSON-RPC 2.0 over stdio implemented on the standard library (`json`, `sys`); the tool schemas are plain JSON Schema dicts. Ruff-based negative tests run `ruff` as a subprocess from `tests/harness/` (the only test directory where TID251 is relaxed, for exactly this reason). |
| Do not | Weaken a lint rule, a CI gate or a negative test. Add a dependency. Create a real target under `targets/` (Phase 4). Implement the drift-triage LLM step. Edit docs/00, 01, 02. Touch the network from a test. |

## Global constraints (copied from the spec)

- A target is exactly the ADR-027 surface: `manifest.yaml`, optional `parser.py`, `README.md`,
  `fixtures/**` (Bronze objects), `tests/golden/*.yaml`, `tests/test_*.py`, empty `__init__.py` ×2.
- Adapters own syntax; the platform owns semantics (ADR-005). No fetch or normalise code in a target.
- Route A touches `targets/<id>/` only; Route B is a platform PR (ADR-022). An unadmitted source
  gets an admission request, never an invented unit.
- MCP wraps the same library as the CLI (ADR-000, ADR-007); in developer mode CI is the enforcement;
  in constrained-agent mode the sandbox is the boundary.
- Fixtures are Bronze objects recorded by `energyctl record-fixture` (opt-in network); goldens are
  YAML with values checked by a human; a target without fixtures or goldens fails collection (ADR-020).
- Images by digest; every migration has a downgrade (ADR-016). Requests/limits on every workload (A-8).
- Unit tests run with sockets disabled; nothing here is `live`.

## Decisions taken by this plan (formalisations, not new policy)

| # | Decision | Why |
|---|---|---|
| P3-D1 | The MCP server speaks JSON-RPC 2.0 over stdio on the standard library (`initialize`, `tools/list`, `tools/call`, `ping`); no MCP SDK. | No dependency without an ADR + allowlist (ADR-006/ADR-019); the protocol subset needed for eight tools is small and fully testable in-process. |
| P3-D2 | `open_pr` **prepares** a PR: it runs every gate on one target and writes a self-contained bundle (title, body, files, gate results) to an outbox; `scripts/apply_pr_bundle.py` turns a bundle into a branch and a commit (never on `main`, never a push without `--push`). | Platform code may not spawn `git` (ADR-027 §3 bans `subprocess`); the push is the Level-2 boundary and stays outside the server (the sandbox's Git sidecar or a human). |
| P3-D3 | The golden runner executes the platform pipeline offline (fixture → decode → generic parser → mapping) and compares expected rows by observation identity. Custom `parser.py` execution stays deferred (P2-D8): the surface check constrains the file, a target's own `tests/test_*.py` may import it statically, and the loader arrives with an ADR when a committed source needs it. | Dynamic import is banned platform-wide; T1–T3 and E1 are generic-parser targets. |
| P3-D4 | Golden file format (`energy_platform.contracts.golden`): `fixture`, `checked_by` (non-empty), `expect.rows[≥1]` **or** `expect.quarantine` (reason substring), optional `expect.row_count`, `expect.quality_events`. A row is `(delivery_start_utc, resolution, metric, value, [dimensions], [source_version])`. | ADR-020: YAML goldens, values checked by a human; 01 §9 negative fixtures expect a quarantine, which is a golden outcome too. |
| P3-D5 | Target completeness (fixture + golden + test module, no placeholder) is enforced twice on purpose: by the surface check in `make lint` and by `conftest.py` at pytest session start (`make test`). | ADR-020 says "fails collection"; `make lint` catches it earlier and the MCP server reuses the same function. |
| P3-D6 | `pr-surface` classification: if a diff touches anything under `targets/`, every changed path must lie under one `targets/<id>/`; `targets/__init__.py` counts as platform. A diff that touches no target is a platform PR and passes this gate (CODEOWNERS is its control). | ADR-022 Route A/B; ADR-006 CODEOWNERS on the platform. |
| P3-D7 | "Normalise code" in `parser.py` is rejected by AST rules: binary `*`, `/`, `//`, `**`; unary `-` applied to anything but a literal; calls to `astimezone`; the `tzinfo=` keyword; calls to `timedelta`. `+`, `-` (binary), `%` stay allowed (string work, index arithmetic). | ADR-005: a parser emits records in the source's vocabulary; units, timezones, intervals and signs are the platform's. The rule set is documented in 05 C-03 so an author knows what to move into the manifest. |
| P3-D8 | "Positional parsing" is rejected by an AST rule (integer-literal subscript in `parser.py`) and a manifest rule (`source` must not be a bare integer). | 05 C-04; header names are the contract with the source (04 §2.8). |
| P3-D9 | `record-fixture` has two modes: `--live` (opt-in network, through the real fetch path and a scratch Bronze) and `--from-file` (offline: build the entry around a saved payload, for the synthetic fixtures 01 §10 asks for until redistribution is confirmed). | ADR-020 and 01 §10 both. |
| P3-D10 | `scripts/check_workloads.py` covers A-8 and ADR-016 on whatever exists now: `.github/workflows/*.yml` action pins, `deployment/**/Dockerfile*` `FROM` digests, and any Kubernetes YAML under `deployment/`; `helm-lint` will feed it the rendered chart in Phase 5. | The chart does not exist yet; the gate and its negative tests must. |

## Ordered tasks

### Task 3.1 — Constraint matrix and plan

**Files:** `docs/05-constraint-matrix.md`, this file.

- [ ] 05 written with every roadmap-mandated row plus the tooling rows (C-01…C-54), the gate inventory and the deferred list.
- [ ] Commit `docs(harness): constraint matrix (05) and Phase 3 plan`.

### Task 3.2 — Harness library: surface check moves into the library, completeness, goldens format

**Files:** `energy_platform/harness/{__init__,surface}.py`, `energy_platform/contracts/golden.py`, `scripts/check_target_surface.py` (thin), `energy_platform/contracts/manifest.py` (numeric `source` rule), `conftest.py` (session-start completeness), `tests/harness/test_target_surface.py`, `tests/harness/test_target_collection.py`, `tests/contracts/test_manifest_negative.py`, `tests/contracts/test_golden.py`.

- [ ] `harness.surface`: existing rules + C-01 URL literal, C-03 normalise AST, C-04 positional AST, C-05 `float(`, C-06 duplicated contracts utility, C-07 `while True`, C-13 placeholders, C-14/C-15 completeness, C-16 golden model, C-18 Bronze fixture integrity, C-19 id mismatch. `check_root`, `check_target`, `completeness(target)` public.
- [ ] `contracts.golden`: `GoldenFile`, `GoldenRow`, `load_golden(path)`.
- [ ] Negative tests per new rule, positive control updated (`make_target` now builds a complete target).
- [ ] Commit `feat(harness): target surface check in the library with completeness, normalise/positional/placeholder rules and the golden file model (05 C-01…C-19)`.

### Task 3.3 — Golden runner and auto-discovery

**Files:** `energy_platform/harness/goldens.py`, `energy_platform/runtime/process.py` (`map_payload` public), `tests/harness/test_goldens.py`, `tests/harness/targets_builder.py` (a complete synthetic target built from `examples/`).

- [ ] `run_golden(target_dir, golden_path) -> GoldenReport` (offline pipeline, identity comparison, quarantine expectation, row_count, quality event kinds); `discover(targets_root)`.
- [ ] `tests/harness/test_goldens.py`: parametrised over `discover(REPO/"targets")` (empty in this phase), plus C-17 negatives on a tmp target and a passing control.
- [ ] Commit `feat(harness): golden runner over the offline pipeline, auto-discovered by the test suite (ADR-020, 05 C-17)`.

### Task 3.4 — Scaffolder, `validate <id>`, `record-fixture`, `run-target-tests`, `admission-request`

**Files:** `energy_platform/harness/{scaffold,fixtures,admission,tests}.py`, `energy_platform/cli.py`, `docs/admissions/TEMPLATE.md`, `Makefile` (`new-target`, `validate-targets`), `tests/harness/test_scaffold.py`, `tests/harness/test_cli_harness.py`.

- [ ] `scaffold_target(root, id, modality, dataset_id, with_parser)` writes exactly the ADR-027 surface; with a registered dataset the contract and mapping skeleton are filled from the registry (units, dimensions), sources left as `REPLACE_ME`.
- [ ] `energyctl validate [ID] [-m PATH] [--all]` (id → `targets/<id>/manifest.yaml`, id/dir mismatch is an error, `--all` for CI).
- [ ] `energyctl record-fixture ID --name N (--live | --from-file PATH)`; `energyctl run-target-tests ID`; `energyctl admission-request ID` → `docs/admissions/<id>.md` from the template with the exact gaps.
- [ ] Tests: scaffold then complete a target with an example fixture and a golden → every gate green (control); scaffold left as is → C-13/C-14/C-15 fire; C-20, C-23, C-50, C-54 negatives.
- [ ] Commit `feat(cli): new-target scaffolder, validate by id, record-fixture (live opt-in / from-file), run-target-tests, admission-request (ADR-022, ADR-027)`.

### Task 3.5 — Repository gates: PR surface, workloads, migrations, CI wrappers

**Files:** `energy_platform/harness/pr_surface.py`, `scripts/check_pr_surface.py`, `scripts/check_workloads.py`, `scripts/check_migrations.py`, `Makefile` (`pr-surface`, `workload-check`, `migration-check`, `harness-check`, `check`), `.github/workflows/ci.yml` (two jobs), `docs/branch-protection.md`, `tests/harness/test_pr_surface.py`, `tests/harness/test_workloads.py`, `tests/harness/test_migrations_gate.py`, `tests/harness/test_ci_wrappers.py`, `tests/harness/test_deps_allowlist.py`.

- [ ] Each gate a pure function plus a thin `main`; negatives C-37…C-46; one git integration test for `pr-surface`.
- [ ] Commit `feat(ci): pr-surface, workload (digest/requests/action pins) and migration-downgrade gates wired through Make (05 C-37…C-46)`.

### Task 3.6 — Ruff negative tests

**Files:** `tests/harness/test_ruff_gates.py`.

- [ ] Run `ruff check --config pyproject.toml --stdin-filename <path> -` on planted snippets: C-08, C-09, C-30 with positive controls (`energy_platform/fetch/…` may import `httpx`).
- [ ] Commit `test(harness): ruff gates proven by planted snippets (05 C-08, C-09, C-30)`.

### Task 3.7 — MCP server and PR bundle

**Files:** `energy_platform/mcp/{__init__,server,tools,repo}.py`, `energy_platform/harness/pr.py`, `scripts/apply_pr_bundle.py`, `energy_platform/cli.py` (`mcp-serve`, `pr-bundle`), `tests/harness/test_mcp.py`, `tests/harness/test_pr_bundle.py`.

- [ ] Tools exactly: `read_repository`, `inspect_target`, `scaffold_target`, `write_target_file`, `validate_target`, `record_fixture`, `run_target_tests`, `open_pr`. Server options: `--root`, `--outbox`, `--allow-network`.
- [ ] Guards: path confinement + deny-list on reads; writes only inside `targets/<id>/`, checked by the surface rules before being kept, journaled; `record_fixture` live only with `--allow-network`; `open_pr` requires one touched target and all gates green.
- [ ] Tests drive the server in-process through the JSON-RPC handler (C-47…C-53) and through the stdio loop once.
- [ ] Commit `feat(mcp): stdio JSON-RPC server exposing the ADR-007 tool set over the harness library; PR bundle + apply script (ADR-007, 05 C-47…C-53)`.

### Task 3.8 — Sandbox recipe and docs

**Files:** `deployment/sandbox/{Dockerfile,README.md}`, `docs/04-contracts.md` §6 (test table rows), `docs/03-roadmap.md` checkboxes, `docs/progress.md`, `CLAUDE.md` (commands line only if changed).

- [ ] Dockerfile: digest-pinned base, non-root, no shell binaries, entrypoint `energyctl mcp-serve`; README: egress limited to the Git remote, how the bundle leaves the sandbox, what the container deliberately lacks.
- [ ] `make workload-check` green on the new Dockerfile and the workflow pins.
- [ ] Commit `docs(harness): sandbox recipe, contracts test table, roadmap and progress for Phase 3`.

## Acceptance for the phase

`make check` green; `make harness-check`, `make workload-check`, `make migration-check`,
`make pr-surface` (no base → honest skip) green; every C-row's test present and passing; `targets/`
still empty except `__init__.py`.
