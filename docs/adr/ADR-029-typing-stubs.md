# ADR-029 — Typing stubs for allowlisted runtime packages

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-20 |
| Resolves | amends ADR-019 (dependency allowlist) and ADR-014 (`mypy --strict`) |
| Supersedes | — |

## Context

ADR-019 approves `pyyaml` as a runtime dependency; it ships no type information. ADR-014 requires
`mypy --strict` everywhere. The first `import yaml` in `energy_platform/contracts/manifest.py`
(Phase 1) fails the type gate with "library stubs not installed". Neither ADR says whether a
`types-*` stub distribution counts as a new dependency needing its own ADR.

## Decision

A `types-<pkg>` stub distribution (typeshed) for a runtime package **already approved by an ADR**
is a **dev-group** dependency covered by that package's ADR. It is listed in `deps-allowlist.txt`
with a comment naming the runtime package it types. It is never a runtime dependency. Any stub
package for a runtime package that is *not* approved needs the runtime package's own ADR first.

## Rationale

The stubs carry no executable code into the platform image and exist only so that the strict type
gate can check code that uses the approved package. The alternative would be to weaken the gate.

## Rejected

- `[[tool.mypy.overrides]] ignore_missing_imports = true` for `yaml` — weakens a CI gate inside a
  task, which CLAUDE.md forbids.
- A hand-written typed wrapper around `yaml.safe_load` marked `# type: ignore` — a suppression
  comment that hides the same gap and drifts from upstream.

## Consequences

- `deps-allowlist.txt` gains `types-pyyaml` under a "stubs (ADR-029)" comment in Phase 1.
- Future approved packages without inline types (`lxml` → `lxml-stubs`, `psycopg` ships its own)
  follow the same rule without a new ADR.
- Devil's advocate: typeshed stubs can lag the package; a mismatch surfaces as a mypy error on
  upgrade and is fixed by pinning the stub, never by suppression.

## Verification refs

none — design decision.
