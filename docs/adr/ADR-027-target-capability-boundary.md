# ADR-027 — Target capability boundary

| | |
|---|---|
| Status | ACCEPTED |
| Amended by | ADR-032 (2026-09-20): §3 names `fetch/objectstore.py` as the object-store client, inside `fetch/` |
| Date | 2026-09-19 |
| Resolves | Codex review F03; amends ADR-014 (egress lint rule) and ADR-017 (parser registration) |
| Supersedes | ADR-014 "lint bans `httpx`/`requests`/`urllib` imports outside `fetch/`" as the statement of the egress guardrail |

## Context

Banning five import names does not stop `http.client`, `socket`, `subprocess` or
`importlib.import_module("requests")`. The review planted a target parser using
`http.client.HTTPSConnection` and every gate stayed green. The documents claimed "all outbound
HTTP goes through `energy_platform.fetch`" without a mechanism. Static lint cannot sandbox
arbitrary Python; it can make the accidental bypass fail loudly and make the deliberate one
visible in review, while the runtime block makes any network use fail the contributor's own
tests.

## Decision

1. **Positive definition of a target.** `targets/<id>/` may contain exactly: `manifest.yaml`,
   `parser.py` (optional), `README.md`, `fixtures/**` (Bronze objects: blob + capture-log entry),
   `tests/golden/*.yaml`, `tests/test_*.py`, and empty `__init__.py` files in `<id>/` and
   `<id>/tests/` (packaging only, so that two targets' `parser.py` are distinct modules). `scripts/check_target_surface.py` (run by `make lint`)
   fails on any other file, and on any of the following inside `targets/`: `# noqa`,
   `# type: ignore`, `# pragma`, `pytest.mark.skip`, `pytest.mark.xfail`, `pytest.importorskip`,
   `__import__`, `exec(`, `eval(`, `open(`, `getattr(__builtins__`, `conftest.py`. The check has a
   negative test per row in `tests/harness/`.

2. **Parser input is decoded by the platform.** `Parser.parse(doc: DecodedDocument) ->
   Iterable[SourceRecord]` (Phase 1 protocol). The platform decodes bytes per the manifest's
   `contract.decode` (`xlsx` → sheets of rows, `xml`/`soap` → a read-only element view,
   `json` → objects, `html-table` → rows, `csv` → rows) before a custom parser sees anything. A
   custom parser therefore needs no third-party import. `parser.py` may import only
   `energy_platform.contracts` and the pure-data standard library modules `decimal`, `datetime`,
   `zoneinfo`, `re`, `typing`, `dataclasses`, `collections`, `enum`, `itertools`, `functools`,
   `math`, `fractions`. Any other import fails the surface check (positive allowlist, not a ban
   list).

3. **Banned-API list for all code outside `energy_platform/fetch/`** (ruff TID251):
   `httpx`, `requests`, `urllib`, `urllib3`, `aiohttp`, `http.client`, `http`, `socket`, `ssl`,
   `ftplib`, `smtplib`, `telnetlib`, `xmlrpc`, `webbrowser`, `subprocess`, `os.system`,
   `os.popen`, `importlib`, `ctypes`, `multiprocessing`, `asyncio.open_connection`. Inside
   `targets/` the positive allowlist of (2) already excludes them; the ban is for the rest of the
   platform, where a positive allowlist is impractical. The object-store client of the Bronze S3
   backend is `energy_platform/fetch/objectstore.py` (ADR-032, 2026-09-20): it lives inside
   `fetch/` so this rule stays literal and there is still exactly one egress package.

4. **Runtime block in unit tests.** `tests/conftest.py` installs an autouse fixture that replaces
   `socket.socket`, `socket.create_connection` and `socket.getaddrinfo` with functions raising
   `RuntimeError("network disabled in unit tests (ADR-027)")` for every test not marked `live`.
   `make test` selects `-m "not live"`. A parser or test that opens a connection fails its own
   test run, on a laptop and in CI, without any network being contacted.

5. **What this is not.** These are guardrails: they stop accidental bypass and make deliberate
   bypass visible in a diff. The boundary for constrained-agent mode is the ADR-007 sandbox
   (container with no shell, egress limited to the MCP server and the Git remote). The
   documents say "guardrail" for (1)–(4) and "boundary" only for the sandbox.

## Rationale

A positive allowlist on the smallest surface (targets) plus a runtime block is enforceable today,
needs no new dependency, and covers the standard-library paths the review used. A ban list on the
larger platform surface is the pragmatic complement.

## Rejected

- Executing target tests in a network namespace (needs privileges CI runners and laptops do not
  uniformly have; the socket block achieves the same for Python code).
- Allowing third-party parsing libraries in `parser.py` (would require a dependency allowlist
  per target and reopens the "syntax only" rule of ADR-005).
- Leaving the five-name ban as is and relying on review (the review demonstrated it fails).

## Consequences

- `pyproject.toml`: banned-api extended; `scripts/check_target_surface.py` added to `make lint`;
  `tests/conftest.py` socket block; negative tests in `tests/harness/`.
- Phase 1: `DecodedDocument` and `contract.decode` in the parser protocol and manifest schema.
- Phase 3 constraint matrix rows: "third-party import in parser", "file outside the target
  surface", "suppression comment in a target", "network call in a unit test".
- Devil's advocate: `zoneinfo` and `decimal` are enough for parsing already-decoded rows; if a
  real source needs more (e.g. a binary format), the platform gains a decoder (platform PR), not
  the target an import.

## Verification refs

`codex-review/evidence/adversarial-probes.json` (P01: `http.client` parser passed all gates at
`7d872ea`).
