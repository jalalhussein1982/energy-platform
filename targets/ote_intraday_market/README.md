# ote_intraday_market — T1, OTE continuous intraday market (SOAP)

Route A adapter (ADR-022): this directory is the whole contribution — a manifest, Bronze fixtures,
goldens and one test module. No fetch, unit, timezone or retry code lives here (ADR-027); the
platform runs the manifest. Contract: `docs/01-data-scope.md` §3 T1. What the live service actually
does, and the evidence for every shape below: `docs/06-source-verification.md` §1–§2 and
`docs/evidence/README.md` (rows 1, 8, 9, 17–19).

**System of record** for `price_vwap` and `volume_total` of `ote.idm_continuous`; the XLSX target
(`ote_intraday_market_xlsx`) stores its copies of the same two metrics and the platform raises
`reconciliation_mismatch` above 0.01 EUR/MWh / 0.001 MWh (01 §3 rule 2). Zero mismatches were seen
live on four days (06 §3.5).

## Fixtures (synthetic copies of the live shape — 01 §10)

Every fixture is a Bronze object written by `energyctl record-fixture --from-file` from a payload
whose element names, item layout and item counts copy the live reads; values are invented
(deterministic formulas, so a reader can check any golden row by opening `fixtures/<name>/blob`).
Live payloads are not committed until OTE confirms redistribution (06 §1.4).

| Fixture | Demonstrates | Expected outcome (golden) |
|---|---|---|
| `ordinary_day` | 96 items, 2026-09-19 | 192 rows, `complete 96/96` |
| `spring_dst_day` | 23-hour day 2026-03-29, 92 items, offset change inside the day | 184 rows, `complete 92/92` |
| `autumn_dst_day` | 25-hour day 2025-10-26, 100 items, the repeated 02:xx hour | 200 rows, `complete 100/100` |
| `hourly_native` | 2024-06-30 at `PeriodResolution` PT60M (pre-July-2024 days are hourly, 06 §2) | 48 rows at PT60M; no resampling |
| `partial_day` | rolling day: only published periods are items (live: 58 at 14:24, row 9) | 116 rows, `partial 58/96` |
| `no_trade_null` | complete day, period 13 has `Volume` 0.000 and no `Price` | `price_vwap` NULL, `volume_total` 0.000, `complete 96/96` |
| `negative_and_zero_price` | −4.21 and 0.00 EUR/MWh kept as published (live minimum −4.21, 06 §1.6) | rows with those values |
| `empty_result` | empty `<Result/>` (day not yet published) | 0 rows, no event, no quarantine |
| `decimal_comma` | `<Price>124,58</Price>` under `decimal_separator: dot` | quarantine `not a decimal under the dot rule` |
| `soap_fault` | SOAP Fault over HTTP 200 | quarantine `SOAP Fault` |
| `emerg_flag` | optional `Emerg` element present, declared in `ignore_fields` (ADR-034) | 16 rows, no `unknown_field` |

Not fixtures, covered by platform tests: an unchanged payload is a stale fetch
(`tests/bronze/test_bronze.py`, `content_changed`), a source-side 5xx versus a local failure
(`tests/runtime/test_crash_matrix.py::test_source_unavailable_writes_nothing_to_bronze_but_records_the_attempt`,
`tests/fetch/test_client.py::test_5xx_exhausting_attempts_raises_fetch_failed`).

## Manifest notes

- `cadence.correction {cron: "7 * * * *", days: 3}` declares the 01 §5 re-poll of D-1..D-3; the
  runtime verb arrives in Phase 5 (ADR-033). Until then a correction is picked up only by a manual
  `energyctl capture --force`.
- `history.max_age: P2Y` is an assumption beyond the one pre-2024-07 day read live.
- `ignore_fields: [Emerg]`: the WSDL's optional flag has no registered metric; registering one is
  Route B, not a change here.

## Checks

```text
energyctl validate ote_intraday_market        # structural + admission: OK
energyctl run-target-tests ote_intraday_market
make check                                    # lint (ADR-027 surface), type, test (goldens auto-discovered), harness-check
energyctl pr-bundle ote_intraday_market       # refused while any gate is red
```
