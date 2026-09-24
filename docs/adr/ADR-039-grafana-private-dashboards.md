# ADR-039 — Grafana dashboards over Silver: a private window, not an endpoint

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-24 |
| Resolves | D-6 mechanics for a human viewer (`02` §4.2: annotations by default, dashboards as JSON); the "cosmetic" visualisation the author asked for after review 2; complements ADR-037 (the SLI) and D-9 (no read API: still true) |
| Supersedes | — |

## Context

The platform's interface is SQL on Silver (D-9) and the freshness SLI is a table exported to
Prometheus metrics (ADR-037), with a Grafana dashboard JSON that needs a Prometheus nobody runs
on the demo. Two weeks of intraday prices with corrections visible, next to the freshness state
of every target, say in one screen what the ADRs say in fifty pages — and a person evaluating
this repository reads screens too.

Two constraints decide the shape. OTE's answer of 2026-09-24 (`06` §1.4) allows internal use only
and forbids publication to third parties; the maintainer's decision for ČEPS (`06` §4.5) is the
same. A dashboard on a public address showing those values is publication. And the chart's
posture — default-deny NetworkPolicies, the restricted pod profile, images by digest, no CRDs in
the core render — is the platform's argument; a viewer must not be its exception.

## Decision

1. **Grafana as an optional chart component**, `grafana.enabled` (off by default; on in the
   `local` profile and the CI all-flags render; on for the demo once its Secret carries the
   keys). One Deployment, one ClusterIP Service on 3000, two ConfigMaps, two NetworkPolicies.
2. **Private by construction.** No Ingress, no LoadBalancer, no NodePort, no firewall change;
   egress to Postgres and DNS only (Grafana is a verb role for the Postgres rule and never a
   fetching role); ingress from the namespace only; anonymous access, sign-up, telemetry, update
   checks and the news feed off; access is `kubectl port-forward` with the admin password from
   the namespace Secret (`GRAFANA_ADMIN_PASSWORD`). A screenshot with source values does not go
   into the public repository.
3. **A read-only database role.** Migration `0007_reader_role` creates the group role
   `energy_reader` with `SELECT` on the schema's tables and views and default privileges for
   later ones (tolerant of a database user without `CREATEROLE`: a notice, an operator step).
   The migrate hook, when Grafana is on, runs `energyctl migrate --reader-user grafana` and
   creates or rotates the login role from `GRAFANA_DB_PASSWORD`. Grafana never holds the
   application's credentials; a compromised dashboard can read, not write.
4. **Provisioned, read-only, stateless.** The datasource and the dashboards are ConfigMaps
   rendered from the chart's `dashboards/` files (`prices.json`: intraday price per period with
   the two OTE transports overlaid, traded volume, day-ahead price, ČEPS load, imbalance
   settlement by version, newest current row per dataset; `freshness-sql.json`: the ADR-037
   states per target, ledger runs by state, capture attempts and quality events per hour,
   version / occurrence / invalidation counts, the newest attempt per target). The data
   directory is an `emptyDir`: nothing edited in the UI survives a restart. The queries read
   the current views, so the dashboard shows exactly what ADR-023 (ownership, occurrences) and
   ADR-038 (invalidations) say is current.
5. **Image by digest** (`docker.io/grafana/grafana:12.2.0`, resolved from the registry's
   manifest index on 2026-09-24), uid 472, read-only root filesystem, requests and limits,
   restricted profile — the same gates as every workload (`05` C-43, C-44, C-57).

## Rationale

A window, not a product: nothing runs on the capture/process path, nothing needs backing up,
and the whole component is a flag and two JSON files that are reviewed like code. Grafana's
provisioning does the work; a custom web application would be a second thing to secure. The
read-only role costs one migration and makes the credential question disappear.

## Rejected

- **A public endpoint** (Ingress with TLS and authentication): forbidden by the sources' terms
  for the data it would show, and a new attack surface on a demo built to have none.
- **Grafana with the application's DSN**: a dashboard that can write.
- **Anonymous viewer access**: the port-forward is already the authentication boundary, but a
  password costs nothing and keeps the pod's own surface closed.
- **The Prometheus dashboard only** (ADR-037): the demo has no Prometheus; the SQL dashboards
  need nothing but the database.
- **A static export for the report**: possible, cheaper, and offered; the author chose the live
  screen.

## Consequences

- `05` C-70; `docs/07` §7.1 (access, what the panels show, why private); README "What runs"
  gains the dashboards; the D-9 row says SQL remains the interface and a private dashboard
  exists. `DEMO_SECRET_KEYS` and `local-secrets` gain `GRAFANA_ADMIN_PASSWORD` and
  `GRAFANA_DB_PASSWORD`; enabling Grafana on an existing deploy is a Secret change first
  (a missing key fails the atomic upgrade, which then changes nothing).
- Known weaknesses: the admin password is a shared credential (one viewer, the author); the
  dashboards depend on the current views' names and columns, so a view change is a dashboard
  change too (the chart test loads both JSON files and checks their datasource references).

## Verification refs

`tests/store/test_migrations.py::test_reader_role_can_select_and_cannot_write` (db),
`tests/harness/test_chart.py::test_grafana_is_off_by_default_and_private_behind_its_flag`,
`make helm-lint` (three renders, digests, restricted PSS); the demo deploy (revision after the
Secret change) with a port-forward render recorded in `docs/07` §7.1.
