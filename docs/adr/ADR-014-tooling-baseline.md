# ADR-014 — Tooling baseline

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-4 (`02-architecture-decisions.md` §4.1) |

## Context

The harness is graded on how mechanically it constrains contributors (ADR-006). Tooling is the first gate. The default in 02 §4.1 is adopted; no verification result touches this item.

## Decision

Python **3.12**; **`uv`** for environments and a **hash-pinned `uv.lock`**; **`ruff`** for lint and format (with banned-API rules: naive `datetime.now()`, bare `except: pass`, `requests`/`httpx` calls without timeout, and any `httpx`/`requests`/`urllib` import outside `energy_platform/fetch/`); **`mypy --strict`**; **`import-linter`** layers (`targets/` may import only `energy_platform.contracts`; `energy_platform/` never imports `targets/`; only `energy_platform/fetch/` may import HTTP clients); **`pre-commit`** running the same hooks CI runs; **CODEOWNERS** on `energy_platform/`, `deployment/`, `docs/adr/`, `deps-allowlist.txt`. All of it is invoked through `make check` = `lint` + `type` + `test`.

## Rationale

One lockfile, one linter, one type checker, all strict, all reachable through Make so that CI and a laptop run the identical command (ADR-015).

## Rejected

Poetry/pip-tools (two tools where `uv` is one); `pylint`/`flake8`/`black` trio (slower, three configs); Python 3.13 (library support for `lxml`/`openpyxl` wheels not uniformly pinned at decision time).

## Consequences

03 Phase 0 deliverables are unchanged; the egress lint rule (A-7) is added to the `ruff` configuration in Phase 0, not later.

## Verification refs

none — design decision (A-7 rationale from `00-assumptions.md` §2).
