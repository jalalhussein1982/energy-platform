# OTE imbalance settlement, final monthly (version 2) — SOAP GetImbalanceSettlementPeriodE

Route A adapter for the contract in
[`docs/admissions/ote_imbalance_settlement.md`](../../docs/admissions/ote_imbalance_settlement.md),
next to `ote_imbalance_settlement` (version 0, daily) and `ote_imbalance_settlement_monthly`
(version 1). Same dataset, same three metrics, same mapping: the response's `Version` is
`source_version`, part of the identity, so the final settlement is a version of its own and never
overwrites versions 0 or 1 (04 §2).

Request: `Version=2`, `StartDate` / `EndDate` = the first and last day of the calendar month
**four months before** the run's month (`{month_start[4]:%Y-%m-%d}`, `{month_end[4]:%Y-%m-%d}`,
ADR-033 amendment 1). Each item carries its own `Date`, which dates the observation. One answer
holds a whole month: about 2 976 PT15M items (≈ 1.1 MB with the unmapped fields).

## Polling

One run a month, on the 1st at 07:37 Prague (ten minutes after the version 1 target). A
correction re-polls that run every day at 07:57 for 31 days (ADR-033 §3; days without a run are
skipped, so this costs one request a day).

Why four months back (docs/06 §9.1, reads of 2026-09-23): version 2 of May was published and
version 2 of June was not, so the final settlement appears roughly 85–115 days after the month
ends. A run on the 1st for month *M−4* first asks ~92 days after that month ended, and the
correction keeps asking until ~123 days. `month_start[3]` would ask at ~62–92 days, mostly before
publication. The exact publication day is not known. Until it appears, the run captures an empty
`Result` and maps no rows. If OTE publishes a month later than ~123 days, that month is missed
by the schedule and needs a backfill. `history.max_age: P1Y`: OTE still served the final
settlement of September 2025 on 2026-09-23.

The freshness SLI's partition is the current delivery day (ADR-037), so this target reads as
`late` by construction. Its data is for a month four months back.

## Fixtures and hand-checked goldens

All payloads are **synthetic** (OTE refused redistribution on 2026-09-24, docs/06 §1.4), wrapped with
`energyctl record-fixture --from-file`. They carry two of the unmapped fields
(`PositiveImbalance`, `NegativeImbalance`) to exercise `ignore_fields`; their position in the item
is illustrative. The one exception is `not_yet_published`: it is byte-identical to OTE's empty
answer, which contains no values.

| Fixture | Demonstrates | Expected |
|---|---|---|
| `march_2026_month` | a whole month; 29 March has 92 periods (01:45 CET → 03:00 CEST); 10 March period 37 has no `SettlCounterImbalancePrice` (NULL); 18 March periods 1–8 are published zeros | 8 916 rows (2 972 items × 3) |
| `october_2025_month` | a whole month; 26 October has 100 periods (02:00 twice: indices 9 and 13 are an hour apart in UTC); 5 October periods 45–56 have negative prices; 12 October period 60 has no `SettlImbalancePrice` (NULL) | 8 940 rows (2 980 items × 3) |
| `not_yet_published` | empty `Result` before the month's final settlement is out | 0 rows, no quality event |

Golden values were read back from each blob with ElementTree. The UTC instants were computed
with `zoneinfo` from local midnight, not from platform output.
