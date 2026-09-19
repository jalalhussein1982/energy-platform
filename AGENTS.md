# energy-platform — agent instructions

## What this is
High-availability ingestion of public intraday energy data (OTE, ČEPS, ENTSO-E) with a
constrained extension path so a junior or an agent can add a target without touching core.

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
make check | make test | make demo | make local-up | make smoke-test
energyctl new-target <id> --modality <m> | energyctl record-fixture <id> | energyctl validate <id>

## Session protocol (docs/03-roadmap.md §0)
Plan into docs/plans/phase-N.md before code. One task, one conventional commit, `make check`
green before every commit. Tick roadmap checkboxes and append to docs/progress.md at the end.

## Hard rules
- Never write fetch or normalise code in targets/. Use the manifest.
- Never add a dependency without docs/adr/ entry + deps-allowlist.txt.
- Never call the network from unit tests. Fixtures are Bronze objects.
- Never edit docs/00, docs/01 or docs/02 inside a task; propose an ADR.
- A target PR touches only targets/<id>/. Anything else is a platform PR.
- Timezones: every datetime is aware; delivery intervals are tstzrange; DST days have 92/100 intervals.
- Decimal comma is common in Czech sources; parse explicitly, never float() on raw strings.
- All outbound HTTP goes through energy_platform.fetch. Images by digest. Every migration has a downgrade.
- The core Helm chart needs no CRDs and passes the restricted Pod Security profile.
- Orchestration is CronJob + run ledger (ADR-003 rev.), not Argo.
- Never weaken a lint rule, a CI gate or a negative test to make a task pass.

## Authority
Level 0 read · Level 1 generate targets · Level 2 propose PRs · Level 3 forbidden:
merge to main, production secrets, terraform apply, kubectl write, prod DB mutation, archive deletion.
