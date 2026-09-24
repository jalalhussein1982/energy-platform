# Plan — Phase 11: Grafana dashboards over Silver (private, optional)

| | |
|---|---|
| Goal | A window onto the collected data and the platform's health: Grafana inside the cluster, behind a chart flag, reached only through the cluster (port-forward), reading Silver through a **read-only** PostgreSQL role, with two provisioned dashboards — prices and load, and freshness/ledger health — over the current views. Nothing public, nothing on the capture/process path. |
| Inputs | ADR-037 (the SLI table, the exporter, the existing Prometheus dashboard JSON), ADR-023 amendments 1–2 (the current views), ADR-026 (default deny; every pod restricted), ADR-016 (images by digest, requests/limits), `06` §1.4 and §4.5 (OTE and ČEPS: internal use only — the reason there is no public endpoint), `05` C-42…C-44, C-56, C-57. |
| Do not | Expose anything outside the cluster (no Ingress, LoadBalancer, NodePort, no firewall change). Give Grafana a role that can write. Put a screenshot with source values into the public repository. Add a CRD or a dependency. Edit `00`, `01`, `02`. |
| Gate | `make check`, `make db-test` (the reader role), `make helm-lint` (three renders, restricted PSS, digests) green before every commit. |

## Decisions

| # | Decision | Why |
|---|---|---|
| P11-D1 | **Private by construction.** ClusterIP Service on 3000, NetworkPolicy egress to Postgres and DNS only, ingress from the namespace only; access is `kubectl port-forward`; anonymous access off; admin password from the namespace Secret (`GRAFANA_ADMIN_PASSWORD`). | The sources allow internal use only (`06` §1.4, §4.5); a public page with their values would publish them. |
| P11-D2 | **A read-only database role, created by the migrations.** Migration `0007_reader_role` creates the group role `energy_reader` (NOLOGIN) with `SELECT` on the schema's tables and views and default privileges for future ones, tolerant of a database user without `CREATEROLE` (cnpg/external: a notice, not a failure). The migrate hook, when `grafana.enabled`, runs `energyctl migrate --reader-user grafana` with the password from `GRAFANA_DB_PASSWORD` and creates or rotates the login role as a member of `energy_reader`. | Grafana never holds the application's credentials; a compromised dashboard can read, not write. The migration is the one place schema-level grants belong; the login role's password is a Secret, never a migration. |
| P11-D3 | **Provisioned, not clicked.** Datasource and dashboards are ConfigMaps rendered from files in the chart (`dashboards/prices.json`, `dashboards/freshness-sql.json`); the existing Prometheus dashboard stays for operator setups. Grafana's data directory is an `emptyDir`: nothing a user edits in the UI survives a pod restart, by design. | Reproducible from the chart; no state to back up; the dashboards are reviewed like code. |
| P11-D4 | **The queries read the current views** (`observations_current_by_transport` for the two OTE transports overlaid, `observations_current` for the rest), so what the dashboard shows is what ADR-023 says is current — including ownership, occurrences and invalidations. | The dashboard is a window, not a second interpretation of the data. |
| P11-D5 | **Image by digest, restricted profile**: `docker.io/grafana/grafana:12.2.0` at `sha256:74144189…` (resolved from the registry's manifest index 2026-09-24), uid 472, read-only root filesystem, writable `emptyDir`s for data and logs, telemetry and update checks off, requests and limits like the exporter's. | `05` C-43, C-44, C-57 apply to every workload. |
| P11-D6 | **Demo enablement is a Secret change first (Level 3).** The two new keys (`GRAFANA_ADMIN_PASSWORD`, `GRAFANA_DB_PASSWORD`) join `DEMO_SECRET_KEYS`; `local-secrets` generates them; the demo Secret is patched by the author (or by the agent with the author's approval), then `values-demo.yaml` turns the flag on. | A missing key fails the atomic upgrade; the order avoids a rollback. |

## Tasks

| # | Task | Acceptance | Commit |
|---|---|---|---|
| 11.1 | Migration `0007_reader_role` (with downgrade); `silver.migrate.grant_reader`; `energyctl migrate --reader-user` with the password from an env var | `make db-test`: the reader can `SELECT` from `observations_current` and cannot `INSERT`; round trip 0001 → 0007 → base → 0007 | `feat(silver): a read-only reader role …` |
| 11.2 | Chart: `grafana.*` values + schema, `templates/grafana.yaml` (ConfigMaps, Service, Deployment, NetworkPolicies), `resources.grafana`, `grafana` in the Postgres-egress roles, the migrate hook's reader step, `secretKeys` text, `local-secrets` and `DEMO_SECRET_KEYS`; two dashboards; enabled in local and all-flags values | `helm-lint` green; chart tests: off by default, on behind the flag, digest and PSS clean, egress = Postgres + DNS, no public rule, datasource `sslmode` per mode, dashboards valid JSON with the datasource uid | `feat(chart): Grafana dashboards over Silver …` |
| 11.3 | ADR-039; `docs/07` §7.1 (access, what the panels show, why private); README ("What runs" gains the dashboards; the D-9 row says a private dashboard exists); `05` C-70; ADR index; roadmap; progress; memory | `make check` green | `docs: Phase 11 …` |
| 11.4 | Demo: the two Secret keys (author / approved), `values-demo.yaml` `grafana.enabled: true`, deploy, verify the reader role and a port-forward render | the migrate hook grants the reader; Grafana pod Ready; a panel returns rows | `feat(demo): Grafana on …` |

## Stop conditions

- The demo Secret cannot be patched → 11.4 stays an author action with the exact commands in the recap and `docs/07` §7.1.
