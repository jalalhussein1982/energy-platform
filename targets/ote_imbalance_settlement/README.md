# OTE imbalance settlement — SOAP GetImbalanceSettlementPeriodE

Route A adapter for the contract in
[`docs/admissions/ote_imbalance_settlement.md`](../../docs/admissions/ote_imbalance_settlement.md).
The manifest uses the platform's generic SOAP parser; the scaffolded test is unchanged.

Source: https://www.ote-cr.cz/pw-data/services/PublicDataService, SOAP 1.1 action
`http://www.ote-cr.cz/schema/service/public/GetImbalanceSettlementPeriodE`.
One request covers one Prague delivery day and asks for **daily settlement (`Version=0`)**.
The response's `Version` becomes `source_version`, part of the observation identity;
versions 1 (monthly) and 2 (final monthly) are supported by the mapping but are **not polled**
by this manifest. Their publication timing remains unverified in the admission.

Only `SystemImbalance` → `system_imbalance` (MWh), `SettlImbalancePrice` →
`imbalance_price` (CZK/MWh), and `SettlCounterImbalancePrice` →
`counter_imbalance_price` (CZK/MWh) are mapped. Signs are preserved without interpretation;
the imbalance sign's physical meaning is unverified. Every other field named in the admission
is explicitly ignored, including optional `Emerg`. An absent metric element is NULL for that
settlement version; a published zero remains zero. Dot decimals and native PT15M/PT60M
resolution are preserved. There is no source publication timestamp.

## Polling assumptions

Poll hourly at minute 17 in Europe/Prague. At minute 37, re-poll the last runs of D-1 through
D-3 to catch delayed daily results and corrections (ADR-033). These are conservative operational
assumptions, not measured publication latency or a guarantee that every late revision is captured.
`history.max_age: P3D` bounds automatic backfill to three days; source retention depth is
unverified. Old hourly and DST fixtures test offline parsing, not availability within this bound.
Monthly/final settlement scheduling needs publication evidence before this target is widened.

## Source shape and licensing

A bounded CLI `record-fixture --live` read on 2026-09-23 for 2026-09-21 returned HTTP 200,
60,245 bytes, 96 PT15M items, and dot decimals. SHA-256:
`a6a5ecdb62b7d54935dedb4c840b8e30fcc09e56f1a9e6182ea3d7ab695e7378`.
The envelope, response, Result and Item element names match the admission and docs/06 §9.
The temporary live fixture was removed after inspection.

OTE Terms of Use: https://www.ote-cr.cz/en/documentation/term-of-use.
Redistribution was refused by OTE on 2026-09-24 (admission and docs/06 §1.4); all committed payloads
are **synthetic**, wrapped as Bronze objects using CLI `record-fixture --from-file`.
No live settlement values are committed.

## Fixtures and hand-checked goldens

| Fixture | Demonstrates | Expected outcome |
|---|---|---|
| `ordinary_day` | 96 PT15M items, all ignored fields present | 288 rows; partition status; first/last values for all three metrics |
| `spring_dst_day` | 2026-03-29 has 92 periods; 01:45 CET → 03:00 CEST | 276 rows; indices 8/9 are contiguous UTC intervals |
| `autumn_dst_day` | 2025-10-26 has 100 periods; repeated 02:00 | 300 rows; indices 9/13 are distinct UTC instants |
| `hourly_day` | 24 PT60M periods on 2024-06-30 | 72 rows; native hourly resolution |
| `edge_values` | Negative and zero values, each metric absent in selected items | 288 rows, including three NULLs; zero retained |
| `settlement_versions` | Same period with versions 0, 1 and 2 and different values | 9 rows with distinct source versions; partial-day partition status |
| `no_result` | Empty Result, not yet published | 0 rows, no quality events |
| `soap_fault` | Fault envelope recorded with HTTP 200 | Quarantine containing `SOAP Fault` |
| `decimal_comma` | Unexpected comma decimal in this dot-decimal SOAP contract | Quarantine containing `not a decimal under the dot rule` |

Each nonempty ordinary synthetic period N publishes N.12500 MWh, (1000+N).250 CZK/MWh,
and (2000+N).750 CZK/MWh. Edge/version fixtures override selected values explicitly.
All ignored fields have distinct synthetic values so accidental mapping is detectable.
The version fixture deliberately combines versions to test identity; it does not claim that a
single live request returns multiple versions.

Golden values were read from the Bronze blobs with ElementTree, then entered by hand;
no platform result was used to generate expected values. UTC timestamps were calculated from
Prague offsets: midnight CEST = 22:00Z the previous day, midnight CET = 23:00Z.
Spring index 9 is 01:00Z; autumn indices 9 and 13 are 00:00Z and 01:00Z respectively.
Every golden includes `checked_by`; human sign-off remains part of PR review (ADR-022).

## CLI checks

```bash
uv run python -m energy_platform.cli validate ote_imbalance_settlement
uv run python -m energy_platform.cli run-target-tests ote_imbalance_settlement
make check
make pr-surface BASE=main
uv run python -m energy_platform.cli pr-bundle ote_imbalance_settlement
```

This target was authored through the command line following docs/08; no MCP server was started.
