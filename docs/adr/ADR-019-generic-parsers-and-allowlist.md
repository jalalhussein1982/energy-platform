# ADR-019 — Generic parsers in v1 and the initial dependency allowlist

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | B-3 (`02-architecture-decisions.md` §4.1) |

## Context

ADR-005: the platform owns generic parsers per modality; a target contributes `parser.py` only when the generic one is insufficient. ADR-006/008: every dependency is allowlisted. Default adopted; no verification result touches this item.

## Decision

- Generic parsers in v1, all five: **html-table**, **xlsx**, **xml/soap**, **json-path**, **csv**. Each implements the same `Parser` protocol and is tested against the fixtures in `01-data-scope.md` §7/§9 (DST days, decimal comma, empty result, changed header).
- Initial `deps-allowlist.txt` (runtime): `pydantic` v2, `lxml`, `openpyxl`, `httpx`, `psycopg` (v3), `alembic`, `sqlalchemy` (core only), `typer`, `pyyaml`, `jsonschema`, `python-dateutil`, `tzdata`. Test/dev: `pytest`, `hypothesis`, `ruff`, `mypy`, `import-linter`, `pre-commit`, `respx`. Everything else needs an ADR.
- No `pandas` in the platform core (float coercion of decimals; 01 §9 requires decimal-safe parsing). Numbers are parsed with `decimal.Decimal` explicitly.

## Rationale

Five parsers cover every committed target and every candidate in 01 §3–§4. A short allowlist is the mechanical form of ADR-006's dependency gate; naming it now lets Phase 0 ship the CI check with real content.

## Rejected

`pandas`/`polars` in core (silent float/timezone coercion); `zeep` for SOAP (SOAP bodies are templates per ADR-005; `lxml` suffices); `beautifulsoup4` (`lxml.html` covers html-table).

## Consequences

Phase 0 writes `deps-allowlist.txt` with this list; Phase 2 implements the five parsers under `energy_platform/parse/`.

## Verification refs

none — design decision.
