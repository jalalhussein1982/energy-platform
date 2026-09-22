# ADR-037 — Availability as freshness: the SLI table, the exporter and the alert rules (ADR-012 written)

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-22 |
| Resolves | ADR-012 (`02-architecture-decisions.md` §2, "locked in principle, unwritten"); D-6 mechanics (`02` §4.2: annotations by default, `PodMonitor` behind a flag) |
| Supersedes | — |

## Context

ADR-012 fixed the direction: the SLI is the age of the newest observation per target relative
to its **expected publication**, alerts fire on staleness rather than pod restarts, and
`source_unavailable` is distinguished from `pipeline_failed`. `01-data-scope.md` §5 defines the
states per target and delivery partition (`pending`, `partial`, `late`, `complete`, and `stale
fetch` for an unchanged 200) and separates source lateness from ingestion failure. Two
constraints shape the mechanism: every workload is a `CronJob` (ADR-003 rev.), so there is no
long-running platform process to scrape; and `http.server` is a banned import outside
`energy_platform/fetch/` (ADR-027 §4, enforced by a negative test on the exemption list), so the
platform does not serve HTTP itself.

## Decision

1. **The SLI is computed by the platform and stored in Postgres.** Migration `0003_freshness`
   adds `target_freshness` (one row per target, upserted):
   `target_id`, `computed_at`, `partition_start`, `expected_by`, `status`
   (`pending | partial | late | complete`), `observed_periods`, `expected_periods`,
   `newest_delivery_start`, `last_capture_at`, `last_capture_outcome`, `stale_fetch_streak`,
   `source_unavailable` (bool), `pipeline_failed` (bool). The gap-detector CronJob runs
   `energyctl gaps --with-freshness`: gap detection first (ADR-031), then one freshness row per
   target. Downgrade drops the table.

2. **Classification (01 §5, made mechanical).** The partition is the current delivery day for
   day-resolution targets (T1, T2, E1) and the current delivery hour for T3; `expected_periods`
   comes from the DST-aware calendar (92/96/100 quarter-hours); `observed_periods` counts distinct
   delivery starts in `observations_current` for the partition; `expected_by` = the last cadence
   instant of the partition + 2 × cadence (ADR-031 tolerance). Status: `pending` before the first
   cadence instant of the partition; `complete` when observed = expected; `late` when `now >
   expected_by`; otherwise `partial`. `stale_fetch_streak` counts consecutive captures with
   `content_changed = false`. `source_unavailable` is true when the newest attempt failed in the
   fetch layer (connection, timeout, HTTP 5xx, 4xx); `pipeline_failed` when it failed anywhere
   after Bronze (decode, parse, mapping, quarantine, store). Both false on success.

3. **Exposure without a Python server.** A `metrics` Deployment runs `postgres_exporter` (image by
   digest, default metrics disabled) with a queries ConfigMap over `target_freshness`, `runs` and
   `run_attempts`:

   | Metric | Labels | Source |
   |---|---|---|
   | `energy_platform_freshness_age_seconds` | `target` | `now() − newest_delivery_start` |
   | `energy_platform_freshness_status_active` (0/1) | `target`, `status` | `status` (one series per 01 §5 state) |
   | `energy_platform_freshness_periods_count` | `target`, `kind=observed\|expected` | the two counts |
   | `energy_platform_source_unavailable` (0/1) | `target` | `source_unavailable` |
   | `energy_platform_pipeline_failed` (0/1) | `target` | `pipeline_failed` |
   | `energy_platform_stale_fetch_streak` | `target` | `stale_fetch_streak` |
   | `energy_platform_runs_total` | `target`, `state` | `count(*) from runs group by` |
   | `energy_platform_freshness_computed_age_seconds` | `target` | `now() − computed_at` (detects a dead gap detector) |

   (Names as exported: `postgres_exporter` appends the column name to the query name, hence
   `_active`, `_count`, `_total`; recorded 2026-09-22 when the exporter was built.)
   The pod carries `prometheus.io/scrape`, `prometheus.io/port`, `prometheus.io/path`
   annotations (D-6 default). `PodMonitor` and `PrometheusRule` render **only** behind
   `metrics.operator.enabled`; the same rules ship as a plain ConfigMap for scrapers without the
   operator. The exporter's `NetworkPolicy` allows egress to Postgres only and ingress on 9187
   from `metrics.scrapeFrom`.

4. **Alert rules** (the SLO per target is the cadence; values are chart defaults):
   - `EnergyPlatformTargetLate` — `energy_platform_freshness_status_active{status="late"} == 1` for
     2 × cadence: **page** — the source is late *and* we have not caught up;
   - `EnergyPlatformPipelineFailed` — `energy_platform_pipeline_failed == 1` for 1 cadence:
     **page** — our incident;
   - `EnergyPlatformSourceUnavailable` — `energy_platform_source_unavailable == 1` for 1 h:
     **warning** — the source's incident (ADR-012: not ours);
   - `EnergyPlatformFreshnessStale` — `energy_platform_freshness_computed_age_seconds > 3 ×
     cadence`: **page** — the gap detector itself stopped;
   - `EnergyPlatformRestoreDrillFailed` — `kube_job_status_failed{job_name=~"restore-drill.*"} > 0`:
     **page** — a backup that could not be restored (needs kube-state-metrics; documented).
   A Grafana dashboard (`deployment/helm/energy-platform/dashboards/freshness.json`) shows age
   per target, status timeline, runs by state and drill outcomes.

## Rationale

Putting the classification in the platform (where the cadence calendar, DST tiling and the
ledger already live) and the transport in a stock exporter keeps one definition of freshness
for the CLI, the tests and the dashboards, and adds no long-running Python process, no new
import exemption and no new dependency. If the assumption "there is a Prometheus-style scraper"
fails, the table is still queryable by SQL and `energyctl freshness` prints the same rows.

## Rejected

- **A Python `/metrics` server in each job or as a sidecar** — needs `http.server` outside
  `fetch/` (banned) or a new dependency (ADR-019 allowlist); short-lived jobs are also not
  scrapable.
- **Pushgateway from each CronJob** — a push path out of every pod, one more component, and it
  hides the "gap detector dead" case that the `computed_age` metric exposes.
- **Alerting on pod restarts / Job failures only** — ADR-012 explicitly rejects it: a ČEPS outage
  at 03:00 is not our incident, and a healthy pod that ingests nothing is.
- **Computing freshness in the exporter's SQL** — the DST calendar and cadence evaluation would
  be duplicated in SQL and drift from the Python definition.

## Consequences

- `02` ADR-012 heading gains "(written 2026-09-22 as ADR-037)"; the ADR index gains this row.
- Library: `energy_platform/runtime/freshness.py`, `store` protocol gains `upsert_freshness` /
  `freshness_rows`; `docs/04-contracts.md` §6 gains the table.
- Chart: `metrics.{enabled,operator.enabled,scrapeFrom,exporterImage}`; the queries ConfigMap
  is the contract between the table and the metric names above.
- Devil's advocate: `postgres_exporter` is one more third-party image (pinned by digest, no
  cluster rights, read-only DSN role). Accepted over writing a server.

## Verification refs

none — design decision; it builds on 2026-09-19 · V-4 · CONFIRMED (prometheus-operator
creatable in-namespace on the reference cluster, hence the flag rather than a requirement).
