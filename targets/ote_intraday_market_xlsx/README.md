# ote_intraday_market_xlsx — T2, OTE continuous intraday market daily results (XLSX)

Route A adapter (ADR-022): this directory is the whole contribution — a manifest, Bronze fixtures,
goldens and one test module. No fetch, unit, timezone or retry code lives here (ADR-027); the
platform runs the manifest. Contract: `docs/01-data-scope.md` §3 T2. What the live page and file
actually look like, and the evidence for every shape below: `docs/06-source-verification.md` §3 and
`docs/evidence/README.md` (rows 7, 12, 13, 20, 21).

**Owner** of `volume_buy`, `volume_sell`, `price_min`, `price_max`, `price_last`. Its copies of
`price_vwap` and `volume_total` are stored under this transport and compared with the SOAP system
of record (`ote_intraday_market`); a difference above 0.01 EUR/MWh / 0.001 MWh is a
`reconciliation_mismatch` event, never a merge (01 §3 rules 2–3). If this file is unavailable the
five XLSX-only metrics are absent; T1 is not a fallback for them (rule 3).

## How the file is found and read

Discovery first (the results page links `IM_15MIN_DD_MM_YYYY_EN.xlsx`), the dated URL template as
fallback. Sheet `IM Results`, title in row 3, **header in row 6** with a line break before each unit
(`Traded volume\n(MWh)`), data from row 7, a footer sentence after the last period. The platform's
XLSX parser folds whitespace in header text and stops at the footer, so the manifest names the
columns as single-line texts. `Period` is a numeric cell (`1.0`), accepted as an index.

## Fixtures (synthetic copies of the live layout — 01 §10)

| Fixture | Demonstrates | Expected outcome (golden) |
|---|---|---|
| `ordinary_day` | 96 rows, 2026-09-19 | 672 rows, `complete 96/96`, no warning |
| `spring_dst_day` | 92 rows with the bridging label `01:45-03:00` (06 §3.4) | 644 rows, `complete 92/92` |
| `autumn_dst_day` | 100 rows with `02:45-02:00` then the repeated `02:xx` labels | 700 rows, `complete 100/100` |
| `partial_day` | all 96 rows present, 10 filled, the rest blank (live: 58 filled at 14:24, 06 §3.3) | 672 rows of which 602 NULL, `partial 10/96` |
| `no_trade_null` | period 13: volumes 0, prices blank | 0 volumes, NULL prices, day complete |
| `negative_and_zero_price` | −4.21 / −9.5 / 0 EUR/MWh kept as published | rows with those values |
| `decimal_comma_string` | a text cell `124,58` under the dot rule | quarantine `not a decimal under the dot rule` |
| `extra_column` | an unlisted column `Note` | rows plus `unknown_field` (the listed `Time interval` stays silent) |
| `changed_unit_header` | `Average price (CZK/MWh)` | quarantine `no header row contains the mapped columns` |

Values are deterministic formulas, so any golden row can be checked by opening
`fixtures/<name>/blob` with a spreadsheet tool (row 6 + period index → sheet row). Live files are
not committed until OTE confirms redistribution (06 §1.4). Stale fetches are covered by the
platform: the file carries `ETag` and `Last-Modified`, the fetch layer sends conditional requests
and Bronze marks an unchanged payload (`tests/bronze/test_bronze.py`).

## Manifest notes

- `ignore_fields: ["Time interval"]` (ADR-034): the label column is display only; the DST bridging
  labels are never parsed.
- `cadence.correction {cron: "9 * * * *", days: 3}` declares the 01 §5 re-poll (runtime verb in
  Phase 5, ADR-033).
- Polling the file every 15 minutes is not yet confirmed with OTE (01 §10 open item).

## Checks

```text
energyctl validate ote_intraday_market_xlsx
energyctl run-target-tests ote_intraday_market_xlsx
make check
energyctl pr-bundle ote_intraday_market_xlsx
```
