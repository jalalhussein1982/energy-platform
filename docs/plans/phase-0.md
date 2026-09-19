# Plan — Phase 0: Repository bootstrap (2026-09-19)

| | |
|---|---|
| Goal | A repository that already enforces the constraints before any domain code exists. Gate: `make check` green on an empty package. |
| Inputs | 03 Phase 0; ADR-014 (tooling), ADR-015 (CI), ADR-019 (allowlist), ADR-016 (digest/migration rules → PR template), A-7 (egress lint), A-14 (restricted PSS → helm-lint target). |
| Do not | Write any parser, fetcher or manifest. Do not choose the Postgres engine (D-2). No runtime dependency that Phase 0 does not use. |
| Environment | `uv` 0.11, Python 3.12.13 present. `helm`, `terraform`, `gitleaks`, `pre-commit` absent locally → the Make targets that need them must **skip honestly** (print why, exit 0) when the thing they check does not exist yet, and **fail** when it exists and the tool is missing. |

## Ordered tasks

| # | Task | Acceptance check | Commit |
|---|---|---|---|
| 0.1 | `.gitignore`; `pyproject.toml` (Python 3.12, `uv`, dev group: pytest, hypothesis, ruff, mypy, import-linter, pre-commit); `ruff` config with DTZ (naive datetime), E722/S110 (bare/swallowed except), S113 (request without timeout), TID251 banned-api for `httpx`/`requests`/`urllib`/`urllib3`/`aiohttp` with per-file allowance for `energy_platform/fetch/**`; `mypy --strict`; `import-linter` layers; `uv.lock` generated | `uv lock` succeeds; `uv.lock` contains `sdist`/`wheel` hashes | `build: pyproject, ruff, mypy, import-linter config` |
| 0.2 | Empty `energy_platform/` (`__init__.py`, `py.typed`, `contracts/__init__.py`), `targets/__init__.py`, `tests/test_placeholder.py` | `uv run pytest` passes; `uv run mypy --strict` passes; `uv run lint-imports` passes | `feat(skeleton): empty platform package and placeholder test` |
| 0.3 | `Makefile`: `check`, `lint`, `type`, `test`, `deps-allowlist`, `secret-scan`, `helm-lint`, `terraform-validate`, `ci-bootstrap`, plus stubs `local-up`, `local-down`, `smoke-test`, `demo`, `new-target` that exit 1 with "not implemented until Phase N" | `make check` green; `make demo` exits 1 with a message | `build(make): targets; check = lint + type + test` |
| 0.4 | `deps-allowlist.txt` (every package in `uv.lock`, header explains ADR rule) + `scripts/check_deps_allowlist.py` | `make deps-allowlist` passes; adding a fake package name to a copy of the lock makes it fail (shown in commit message) | `build(deps): lockfile allowlist and CI check` |
| 0.5 | `scripts/secret_scan.py` (regexes: AWS key ids, private keys, bearer/API tokens, `password=`), wired to `make secret-scan` | passes on the repo; a temp file with a fake AWS key id fails it | `build(ci): secret scan` |
| 0.6 | `.github/workflows/ci.yml` — one job per Make target, each step = checkout, `make ci-bootstrap`, `make <target>`; `.pre-commit-config.yaml` with local hooks calling `make lint` / `make type` | YAML contains no shell other than `make …`; `python -c "import yaml"`-style parse check | `ci: GitHub Actions thin wrappers over Make (ADR-015)` |
| 0.7 | `CLAUDE.md` + identical `AGENTS.md` from 03 Appendix B (as reconciled) | `diff CLAUDE.md AGENTS.md` empty | `docs: CLAUDE.md and AGENTS.md` |
| 0.8 | `CODEOWNERS`, `.github/pull_request_template.md` (checklist mirroring the Phase 3 minimum constraint rows + ADR-016 rules), `docs/branch-protection.md` | files exist; owners placeholder flagged in progress | `docs: CODEOWNERS, PR template, branch protection notes` |
| 0.9 | `docs/threat-model.md` stub: one heading per ADR-008 catalogue item, each with Mechanism / Gate / Residual risk placeholders | 10 headings present | `docs(threat-model): stub with ADR-008 catalogue` |
| 0.10 | Tick Phase 0 checkboxes in 03; append to `docs/progress.md` with the Phase 1 prompt | `make check` green; boxes ticked | `docs(roadmap): Phase 0 done` |

## Verification before each commit

`make check` (from 0.3 onward; before that the equivalent `uv run` commands).

## Stop conditions

- A deliverable needs a decision not in the ADRs (e.g. a new dependency) → stop, ask one question.
- Anything would require a runtime dependency → defer to the phase that uses it.
