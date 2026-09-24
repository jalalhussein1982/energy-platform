# OTE imbalance settlement, monthly (version 1) — SOAP GetImbalanceSettlementPeriodE

Route A adapter for the contract in
[`docs/admissions/ote_imbalance_settlement.md`](../../docs/admissions/ote_imbalance_settlement.md),
next to `ote_imbalance_settlement` (version 0, daily). Same dataset, same three metrics, same
mapping: the response's `Version` is `source_version`, part of the identity, so the monthly
settlement is a version of its own and never overwrites the daily one (04 §2).

Request: `Version=1`, `StartDate` / `EndDate` = the first and last day of the **previous
calendar month** (`{month_start[1]:%Y-%m-%d}`, `{month_end[1]:%Y-%m-%d}`, ADR-033 amendment 1).
Each item carries its own `Date`, which dates the observation. One answer holds a whole month:
about 2 976 PT15M items (≈ 0.9–1.9 MB).

## Polling

One run a month, on the 1st at 07:27 Prague. A correction re-polls that run every day at 07:47
for 31 days (ADR-033 §3; days without a run are skipped, so this costs one request a day).
Evidence (docs/06 §9.1, 2026-09-23): version 1 of 31 August was published by 23 September, so a
month's settlement lands inside the window. The exact publication day is not known. Until it
appears, the run captures an empty `Result` and maps no rows. `history.max_age: P1Y`: OTE still
served the final settlement of September 2025 on 2026-09-23.

The freshness SLI's partition is the current delivery day (ADR-037), so this target reads as
`late` by construction. Its data is for last month.

## Fixtures and hand-checked goldens

All payloads are **synthetic** (OTE refused redistribution on 2026-09-24, docs/06 §1.4), wrapped with
`energyctl record-fixture --from-file`. The one exception is `not_yet_published`: it is
byte-identical to OTE's empty answer, which contains no values.

| Fixture | Demonstrates | Expected |
|---|---|---|
| `march_2026_month` | a whole month; 29 March has 92 periods (01:45 CET → 03:00 CEST); 15 March period 50 has no `SettlImbalancePrice` (NULL); 22 March is published zeros | 8 916 rows (2 972 items × 3) |
| `october_2026_month` | a whole month; 25 October has 100 periods (02:00 twice: indices 9 and 13 are an hour apart in UTC) | 8 940 rows |
| `not_yet_published` | empty `Result` before the month is settled | 0 rows, no quality event |

Golden values were read back from each blob with ElementTree. The UTC instants were computed
with `zoneinfo` from local midnight, not from platform output.
