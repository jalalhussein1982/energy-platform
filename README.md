# energy-platform

High-availability ingestion of public intraday energy data — OTE continuous intraday market results,
ČEPS system load; ENTSO-E optional (see `docs/01-data-scope.md` §3) — with a constrained extension path, so that a junior engineer or a coding agent can add a target
without touching the core.

Status: **Phase 0 — repository bootstrap.** No platform code yet. Start with
`docs/00-assumptions.md`, `docs/02-architecture-decisions.md`, `docs/adr/` and `docs/03-roadmap.md`.

```bash
make check     # lint + type + test
```

The full README (reproduce block, architecture, how targets are added, how agents are
constrained, assumptions and what they cost) is a Phase 8 deliverable.
