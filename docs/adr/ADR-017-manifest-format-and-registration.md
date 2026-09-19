# ADR-017 — Manifest format and target registration

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-1 (`02-architecture-decisions.md` §4.1) |

## Context

ADR-005/ADR-013: one declarative manifest per target, validated by the platform. B-1 asks for the format, schema versioning, parser registration, and secret references. Default adopted; no verification result touches this item.

## Decision

- Format: **YAML** (`targets/<id>/manifest.yaml`), one document, no anchors/merges, no custom tags.
- Schema: **versioned JSON Schema** exported from the Pydantic model (`schemas/manifest.v1.json`); every manifest declares `schema_version: 1`; a breaking change bumps the major and ships a converter.
- Parser registration: **directory convention** — if `targets/<id>/parser.py` exists it must expose exactly one class implementing the `Parser` protocol; no entry points, no registry file.
- Secrets: manifests never contain values; they contain a **`secretRef`** (`{name, key}`) resolved by the platform from the Kubernetes `Secret` (or env in `local`). CI rejects any manifest whose `fetch` block contains a string matching a token pattern.
- Mandatory fields (ADR-008/013): `license`, `terms_url`, `allowed_hosts`, `cadence`, `modality`, `fetch`, `mapping`.

## Rationale

YAML is what juniors and agents already write; the JSON Schema is what CI and the MCP server validate; directory convention keeps "add a target = add a directory" literally true (ADR-005).

## Rejected

TOML (weaker nesting for `mapping` blocks); entry-point registration (requires editing `pyproject.toml`, which is outside `targets/<id>/`); inline secrets or `${ENV}` interpolation in manifests (leaks into fixtures and logs).

## Consequences

Phase 1 implements `energy_platform/contracts/manifest.py`; Phase 3 constraint matrix rows "missing `license`", "host not in allowlist", "secret in code" gate this ADR.

## Verification refs

none — design decision.
