# ceps_load — T3, ČEPS transmission-system load (SOAP `Load`, QH / AVG / RT)

Route A adapter (ADR-022): this directory is the whole contribution — a manifest, Bronze fixtures,
goldens and one test module. No fetch, unit, timezone or retry code lives here (ADR-027); the
platform runs the manifest. Contract: `docs/01-data-scope.md` §3 T3. What the live service does,
and the evidence for every shape below: `docs/06-source-verification.md` §4 and
`docs/evidence/README.md` (rows 2, 14–16, 22–24).

Two metrics from one item: `@value1` = "Load including pumping [MW]" → `load_incl_pumping`,
`@value2` = "Load [MW]" → `load`. Identity: `(area = CZ, delivery_start_utc, PT15M,
aggregation_function = AVG, version = RT)`; the `version` dimension is the manifest's constant
`source_version` (04 §2.3).

## Time semantics (review F13, resolved)

`@date` names the **start** of the quarter-hour and carries the local offset. Verified on
2026-09-20 by two checks on the same service (06 §4.4): each HR item labelled `h:00` equals the mean
of the QH items `h:00 … h:45` (max deviation 3.2 MW, the minute-weighting residual; the end-labelling
reading is off by up to 872 MW), and the DY item equals the mean of the 96 QH items labelled
`00:00 … 23:45`. The interface description v3.2 defines AVG as the average minute power over the
aggregation but is silent on the edge. The manifest therefore declares `interval_label: start`
without an `[UNVERIFIED]` tag; the goldens below are authoritative.

## Fixtures (synthetic copies of the live shape — 01 §10)

The payloads copy the live response (06 §4.2): the `StructuredData/1.0` namespace, the
`information` block with `name`, `date_from`, `date_to`, `version`, `function`, `aggregation`, the
two `serie` declarations and one `item` per quarter-hour with 0–3 decimals. Values are invented,
deterministic formulas; any golden row can be checked with `grep '<item date="…"' fixtures/<name>/blob`.

| Fixture | Demonstrates | Expected outcome (golden) |
|---|---|---|
| `ordinary_day` | 96 items, 2026-09-19 | 192 rows, `complete 96/96` |
| `spring_dst_day` | 92 items; `01:45+01:00` is followed by `03:00+02:00` (live pattern) | 184 rows, `complete 92/92` |
| `autumn_dst_day` | 100 items; `02:00…02:45` twice, first `+02:00` then `+01:00` | 200 rows, `complete 100/100` |
| `partial_day` | 56 items published so far | 112 rows, `partial 56/96` |
| `missing_value` | item without `@value2` | `load` NULL, `load_incl_pumping` present, day complete |
| `negative_load` | `@value1 = -12.5` | row kept, `negative_value` warning (registry: expected ≥ 0, not enforced) |
| `empty_data` | `<data/>` | 0 rows, no event |
| `decimal_comma` | `@value1 = "5951,667"` | quarantine `not a decimal under the dot rule` |
| `soap_fault` | SOAP Fault over HTTP 200 | quarantine `SOAP Fault` |

Live payloads are not committed: ČEPS's web-service terms and redistribution are still open items
of the 01 §10 register (06 §4.5). Observed but not fixture-worthy: on 2026-09-19 `@value1` equalled
`@value2` on every QH and HR item while the DY item differed — a question for ČEPS (06 §4.2).

## Manifest notes

- Requests use the local Prague clock without an offset (interface description: "the system does
  not process time zone offsets"); `dateTo` is inclusive (`T23:59:59`).
- `cadence.correction {cron: "11 * * * *", days: 1}` declares the 01 §5 one-day correction window
  (runtime verb in Phase 5, ADR-033). Publication cadence and history depth stay `[UNVERIFIED]`
  until the campaign of 06 §6 runs.
- `robots.txt` disallows all crawling; only the documented web service is called (01 §10).

## Checks

```text
energyctl validate ceps_load
energyctl run-target-tests ceps_load
make check
energyctl pr-bundle ceps_load
```
