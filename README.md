# energy-platform

High-availability ingestion of public intraday energy data — OTE continuous intraday market results,
ČEPS system load; ENTSO-E optional (see `docs/01-data-scope.md` §3) — with a constrained extension path, so that a junior engineer or a coding agent can add a target
without touching the core.

Status: **Phase 6 (2026-09-23) — threat model, drift triage, the contributor guide.** Four
committed targets (T1, T2, T3, E1) run as CronJobs from one Helm chart on the live demo cluster
(Hetzner k3s, deployed by GitHub OIDC; Bronze replicated to OCI; a restore drill from the replica
passed), and on a laptop with `make local-up`.

**Adding a target (a data source): read [`docs/08-adding-a-target.md`](docs/08-adding-a-target.md)
— it is the whole procedure.** Architecture: [`docs/architecture.md`](docs/architecture.md);
threat model: [`docs/threat-model.md`](docs/threat-model.md).
Start with `docs/00-assumptions.md`, `docs/02-architecture-decisions.md`, `docs/adr/`,
`docs/04-contracts.md`, `docs/03-roadmap.md` and the runbook `docs/07-operations.md`; the session
log is `docs/progress.md`.

```bash
make check                      # lint (incl. target surface) + lock-check + type + test (network disabled) + harness gates
make db-test                    # store suite + migration up/down round trip on an ephemeral local PostgreSQL
make demo                       # the offline end-to-end path on the three example fixtures (needs initdb/pg_ctl)
make helm-lint terraform-validate   # chart renders (tenant, local, all flags) through the digest / PSS gates; both Terraform roots with mock providers

# reproduce the running system on a laptop (Docker with >= 4 GB, kind, helm, kubectl, uv):
make local-up                   # kind + Cilium + registry → image by digest → secrets → atomic deploy (migrate, smoke hooks) → egress test
make smoke-test                 # helm test (the smoke hook again), freshness metric present, restore-drill dry run
make rollback-drill             # two failing upgrades (smoke, storage probe) must roll back with data untouched
make local-down
```

The full README (architecture, how targets are added, how agents are constrained, assumptions
and what they cost, the live demo hand-over) is a Phase 8 deliverable.
