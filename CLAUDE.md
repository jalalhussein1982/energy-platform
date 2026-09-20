# energy-platform — agent instructions

## What this is
High-availability ingestion of public intraday energy data — OTE continuous intraday market (SOAP +
XLSX), ČEPS load; ENTSO-E optional — with a constrained extension path so a junior or an agent can
add a target without touching core. Committed scope: docs/01-data-scope.md §3 (T1, T2, T3 + demo E1).

## Read first
docs/00-assumptions.md, docs/02-architecture-decisions.md (frozen), docs/adr/ (accepted),
docs/04-contracts.md, docs/05-constraint-matrix.md. Then the current phase in docs/03-roadmap.md.

## Layout
energy_platform/   core library — semantics live here (fetch, bronze, parse, mapping, silver, ledger)
targets/<id>/      manifest.yaml, optional parser.py, fixtures/, tests/  — syntax only
deployment/        helm/, local/, tenant/, own-cluster/terraform/, sandbox/
docs/              assumptions (00), decisions (02), contracts, roadmap, threat model, ADRs
scripts/           helpers invoked only by Make targets

## Commands
make check | make test | make demo | make local-up | make smoke-test | make harness-check | make pr-surface BASE=<ref>
energyctl new-target <id> --modality <m> | energyctl record-fixture <id> --name <n> (--live | --from-file F) | energyctl validate <id>
energyctl run-target-tests <id> | energyctl admission-request <id> | energyctl pr-bundle <id> | energyctl mcp-serve

## Session protocol (docs/03-roadmap.md §0)
Plan into docs/plans/phase-N.md before code. One task, one conventional commit, `make check`
green before every commit. Tick roadmap checkboxes and append to docs/progress.md at the end.

## Hard rules
- Never write fetch or normalise code in targets/. Use the manifest.
- Never add a dependency without docs/adr/ entry + deps-allowlist.txt.
- Never call the network from unit tests. Fixtures are Bronze objects.
- Never edit docs/00, docs/01 or docs/02 inside a task; propose an ADR.
- A target PR touches only targets/<id>/ (the ADR-027 surface: manifest, optional parser, README, fixtures, golden tests). Anything else is a platform PR.
- Registry entries (dataset, metric, host) are platform PRs (ADR-022). An unadmitted source gets an admission request, never an invented unit.
- Timezones: every datetime is aware; delivery intervals are tstzrange; DST days have 92/100 intervals.
- Decimal comma is common in Czech sources; parse explicitly, never float() on raw strings.
- All outbound HTTP goes through energy_platform.fetch. Images by digest. Every migration has a downgrade.
- The core Helm chart needs no CRDs and passes the restricted Pod Security profile.
- Orchestration is CronJob + run ledger (ADR-003 rev.), not Argo.
- Never weaken a lint rule, a CI gate or a negative test to make a task pass.
- Unit tests run with sockets disabled (ADR-027); a test that needs the network is marked `live` and never runs in CI.

## Authority
Level 0 read · Level 1 generate targets · Level 2 propose PRs · Level 3 forbidden:
merge to main, production secrets, terraform apply, kubectl write, prod DB mutation, archive deletion.
