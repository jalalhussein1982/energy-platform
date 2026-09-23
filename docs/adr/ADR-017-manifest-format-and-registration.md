# ADR-017 — Manifest format and target registration

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-1 (`02-architecture-decisions.md` §4.1) |
| Amended by | ADR-027 (2026-09-19): parser input is a platform-decoded document; `parser.py` imports are positively allowlisted. ADR-022/ADR-026: `contract.dataset_id` and `allowed_hosts` must exist in platform registries. Amendment 1 (2026-09-23, below): a target's `secretRef` is scoped to the target |

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

## Amendment 1 (2026-09-23) — a target's `secretRef` is its own

The resolver read any `<NAME>_<KEY>` from the pod environment, and the platform's own
credentials live there (`BRONZE_*`, `POSTGRES_*`). So `{name: BRONZE, key: secret-access-key}`
in a manifest's `auth` would have sent the store-A key to a registered host (threat model §4).
From now on `secretRef.name` must be `target-<target_id>` (`_` → `-`) and `key` alphanumeric,
which gives the environment form `TARGET_<TARGET_ID>_<KEY>`. Manifest validation refuses
anything else, and `fetch_for_manifest` wraps every resolver in `ScopedSecretResolver`, which
refuses it again for a manifest that skipped validation. `05` C-63; `04` §3.4.

## Verification refs

none — design decision.
