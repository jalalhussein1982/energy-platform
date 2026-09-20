# energy-platform

High-availability ingestion of public intraday energy data — OTE continuous intraday market results,
ČEPS system load; ENTSO-E optional (see `docs/01-data-scope.md` §3) — with a constrained extension path, so that a junior engineer or a coding agent can add a target
without touching the core.

Status: **Phase 2 done (2026-09-20) — contracts and the core library.** `make demo` runs
fixture → capture → Bronze → parse → map → PostgreSQL → query offline; no target exists yet
(Phase 3 builds the harness that constrains target-writing first). Start with
`docs/00-assumptions.md`, `docs/02-architecture-decisions.md`, `docs/adr/`, `docs/04-contracts.md`
and `docs/03-roadmap.md`; the session log is `docs/progress.md`.

```bash
make check     # lint (incl. target surface) + lock-check + type + test (network disabled)
make db-test   # store suite + migration up/down round trip on an ephemeral local PostgreSQL
make demo      # the offline end-to-end path on the three example fixtures (needs initdb/pg_ctl)
```

The full README (reproduce block, architecture, how targets are added, how agents are
constrained, assumptions and what they cost) is a Phase 8 deliverable.
