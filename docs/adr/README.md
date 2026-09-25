# ADR log

Every architecture decision, in order. ADR-000 … ADR-013 are sections of
[`02-architecture-decisions.md`](../02-architecture-decisions.md) (frozen); ADR-014 onwards are files
in this directory. All are **ACCEPTED**; amendments are listed where they happened. New ADRs start
from [`ADR-template.md`](ADR-template.md). Open items `D-1 … D-13` are in `02` §4.2.

| ADR | Decision | Where | Amended / written by |
|---|---|---|---|
| ADR-000 | One platform library, many clients (CLI, MCP, CI are thin clients) | `02` | — |
| ADR-001 | Deployment abstraction: one chart, profiles differ only in values and Terraform | `02` | [ADR-001 amend](ADR-001-amend-three-profiles.md): three profiles (`local`, `tenant`, `own-cluster`) |
| ADR-002 | Storage and recovery model: immutable Bronze, authoritative Postgres Silver, independent copy, restore drill | `02` | [ADR-036](ADR-036-object-stores-and-backups-per-profile.md): backup tooling (base backup + WAL by `rclone`) |
| ADR-003 | Orchestration | `02` | [ADR-003 rev.](ADR-003-rev-orchestration-without-crds.md): CronJob + Postgres run ledger, no CRDs |
| ADR-004 | Runtime availability model | `02` | [ADR-024](ADR-024-capture-recovery-invariants.md): capture durability and recovery invariants |
| ADR-005 | Canonical extension contract: targets declare, the platform fetches, parses and maps | `02` | [ADR-027](ADR-027-target-capability-boundary.md): the target capability boundary |
| ADR-006 | Agent authority model (Level 0 read … Level 3 forbidden) | `02` | — |
| ADR-007 | MCP: the golden path as eight tools; constrained-agent sandbox | `02` | — |
| ADR-008 | Prompt-injection and supply-chain threat model | `02` | written out in [`threat-model.md`](../threat-model.md) (Phase 6) |
| ADR-009 | LLM backend: an OpenAI-compatible Protocol; LLM down → platform unaffected | `02` | stub backend, Phase 6 (plan P6-D4) |
| ADR-010 | Local reproduction: `make local-up && make smoke-test`, no credentials | `02` | — |
| ADR-011 | Canonical schema (in principle) | `02` | [ADR-018](ADR-018-canonical-schema-details.md): the details |
| ADR-012 | Availability as freshness (in principle) | `02` | [ADR-037](ADR-037-freshness-sli.md): the SLI table, exporter and alert rules |
| ADR-013 | Manifest schema (in principle) | `02` | [ADR-017](ADR-017-manifest-format-and-registration.md): format and registration |
| [ADR-014](ADR-014-tooling-baseline.md) | Tooling baseline (uv, ruff, mypy strict, import-linter, pytest) | file | — |
| [ADR-015](ADR-015-ci-platform.md) | CI platform: GitHub Actions as a thin wrapper over Make | file | porting note: [`ci-porting.md`](../ci-porting.md) |
| [ADR-016](ADR-016-release-and-rollback.md) | Release and rollback model: images by digest, atomic upgrades, rollback drill | file | [ADR-025](ADR-025-upgrade-hooks-and-install-ordering.md): hooks as the upgrade gate |
| [ADR-017](ADR-017-manifest-format-and-registration.md) | Manifest format and target registration | file | amendment 1 (2026-09-23): a target's `secretRef` is `target-<id>` only |
| [ADR-018](ADR-018-canonical-schema-details.md) | Canonical schema details (bitemporal, identity, current view) | file | — |
| [ADR-019](ADR-019-generic-parsers-and-allowlist.md) | Generic parsers in v1 and the initial dependency allowlist | file | — |
| [ADR-020](ADR-020-test-strategy.md) | Test strategy: fixtures are Bronze objects, goldens by hand | file | — |
| [ADR-021](ADR-021-bronze-tiering.md) | Bronze cold tier as a platform tiering job | file | [ADR-025](ADR-025-upgrade-hooks-and-install-ordering.md): storage probe as a hook |
| [ADR-022](ADR-022-source-admission-vs-adapter-addition.md) | Source admission (Route B) versus adapter addition (Route A) | file | — |
| [ADR-023](ADR-023-derivation-identity.md) | Derivation identity and current-view selection | file | amendment 1 (2026-09-24): the owning transport ranks first in the current view; per-transport current rows (review 2 DC-03); amendment 2 (2026-09-24): occurrences — a returning payload is current again (DC-04); amendment 3 (2026-09-25): the identity carries the implementation — package version plus source digest (review 3 R4) |
| [ADR-024](ADR-024-capture-recovery-invariants.md) | Capture durability, orphan reconciliation, backfill versus replay, lease fencing | file | amendment 1 (2026-09-24): capture generations — a recapture fences in-flight claims, reconcile advances a run to a newer payload, window + correction days (review 2 DC-01, DC-02); amendment 2 (2026-09-24): an abandoned replay attempt is reclaimed (DC-05); amendment 3 (2026-09-24): capture-log entries are created, never overwritten (DC-06) |
| [ADR-025](ADR-025-upgrade-hooks-and-install-ordering.md) | Upgrade verification hooks and first-install ordering | file | — |
| [ADR-026](ADR-026-egress-boundary.md) | Egress boundary: coarse NetworkPolicy plus host enforcement in the fetch layer | file | amendment 1 (2026-09-23): response-body cap (64 MiB, streamed); amendment 2: policy gate where a CNI enforces asynchronously; amendment 3 (2026-09-24): the FQDN layer replaces the coarse public rule; a policy canary the pod's own policy drops — the cluster DNS metrics port; the node's address was tried and withdrawn on kube-router (review 2 DEP-03, DEP-05) |
| [ADR-027](ADR-027-target-capability-boundary.md) | Target capability boundary | file | [ADR-032](ADR-032-object-store-client.md): the object-store client lives in `fetch/` |
| [ADR-028](ADR-028-demo-environment.md) | Demo environment: Hetzner cluster, OCI second store; MetaCentrum stays reference | file | [ADR-035](ADR-035-own-cluster-stack.md) §4: the API port for GitHub-hosted deploys; amendment 1 (2026-09-25): the availability boundary stated — recoverable single-primary, no automatic failover; a failover demonstration is the author's decision (review 3 R1) |
| [ADR-029](ADR-029-typing-stubs.md) | Typing stubs for allowlisted runtime packages | file | — |
| [ADR-030](ADR-030-postgres-engine-plain.md) | Postgres engine: plain PostgreSQL, no TimescaleDB | file | — |
| [ADR-031](ADR-031-gap-detector-defaults.md) | Gap detector internals: expected instants from the cadence, tolerance 2× cadence | file | amendment 1 (2026-09-25): a scheduled capture is keyed by the schedule's instant (the CronJob's tick from the Job name, else the newest firing instant), never the pod's start time (review 3 R2) |
| [ADR-032](ADR-032-object-store-client.md) | Object-store client for the Bronze S3 backend (Option B: own SigV4 client) | file | — |
| [ADR-033](ADR-033-polling-cadence-and-correction-window.md) | Polling cadence, politeness and the correction window | file | amendment 1 (2026-09-23): `month_start[k]` / `month_end[k]`, strict template fields; amendment 2: a capture is about its own delivery day (discovery, baseline); amendment 3 (2026-09-24): cadence aligned to OTE's stated expectation (once-daily corrections, E1 four reads after 13:05) |
| [ADR-034](ADR-034-mapping-ignore-fields.md) | `mapping.ignore_fields`: display-only source fields | file | — |
| [ADR-035](ADR-035-own-cluster-stack.md) | `own-cluster` stack: k3s on plain VMs by cloud-init, four Terraform modules, two roots | file | amendment 1 (2026-09-23): cloud-init first boot only, `make demo-reconfigure`; deploy identity pinned to the workflow; `Role` without `secrets`/`exec` |
| [ADR-036](ADR-036-object-stores-and-backups-per-profile.md) | Object stores per profile, Bronze replication, Postgres backups without a custom image | file | amendment 1 (2026-09-23): bounded backup footprint, per-cluster archive paths; amendment 2 (2026-09-24): RPO per failure domain, replication follows the cadence, staleness alerts (review 2 DEP-01); amendment 3 (2026-09-24): cnpg/external refuse the restore drill until their backup chain exists (DEP-02); amendment 4 (2026-09-24): the local profile's stores are RustFS after MinIO's withdrawal; amendment 5 (2026-09-25): the drill rebuilds the cohort first, compares within lineage and guarantees values, not derivation ids (review 3 R5, R6) |
| [ADR-037](ADR-037-freshness-sli.md) | Availability as freshness: the SLI table, the exporter and the alert rules | file | amendment 1 (2026-09-24): a target's freshness is its own current rows, every mapped metric; month partitions for month-offset targets (review 2 DC-08) |
| [ADR-038](ADR-038-durable-invalidation-decisions.md) | Durable invalidation decisions: a Bronze object per decision, mirrored by reconcile; never current, replayed or restored (review 2 DC-07) | file | — |
| [ADR-039](ADR-039-grafana-private-dashboards.md) | Grafana dashboards over Silver: a private window (port-forward, read-only role, provisioned dashboards), never an endpoint — the sources allow internal use only | file | — |
| [ADR-040](ADR-040-alert-evaluation-and-delivery.md) | Alert evaluation and delivery in the chart: Prometheus over the existing rules, namespaced kube-state-metrics, Alertmanager, the platform receiver; the delivery drill (review 3 R3) | file | amendment 1 (2026-09-25): the operator's channel — its credential from `alerting.alertmanager.existingSecret` (read-only, optional), a credential in values and a route to an undeclared receiver refused at render, the interim night-time routing as a tested values example, the runbook `07` §7.3 |
