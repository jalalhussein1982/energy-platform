# OTE imbalance settlement

Route A adapter for SOAP `GetImbalanceSettlementPeriodE` at
https://www.ote-cr.cz/pw-data/services/PublicDataService. Contract:
[admission](../../docs/admissions/ote_imbalance_settlement.md), dataset
`ote.imbalance_settlement` 1.0.0. Uses the platform's generic SOAP parser; no custom code.

The three admitted metrics are `system_imbalance` (MWh), `imbalance_price` and
`counter_imbalance_price` (CZK/MWh). Values use a decimal dot and retain their published sign;
the physical meaning of the system imbalance sign is unverified. An absent metric element is
NULL, meaning not yet published for this version; a published zero remains zero. All eleven
non-admitted fields named in the admission are explicitly ignored.

`Date`, `PeriodIndex` and `PeriodResolution` locate the Europe/Prague delivery interval.
The response's `Version` becomes `source_version`, part of observation identity alongside
bidding zone CZ, delivery start and resolution. Daily (0), monthly (1) and final monthly (2)
versions remain distinct. No publication timestamp is invented.

## Polling and limits

The request selects **daily version 0** for the run's delivery day. Hourly polling at minute 17
and hourly corrections at minute 37 for D-1 through D-3 are conservative **assumptions**, not
measured publication timing. Corrections re-fetch existing runs (ADR-033); missed runs need the
platform's backfill/reconcile path. `history.max_age: P3D` is a conservative operational limit,
not a claim about OTE retention. It allows the previous three delivery days to be revisited.
Publication latency, sufficient correction depth, historical retention, and the appearance of
monthly/final results remain unverified.

The mapper accepts versions 1/2 and historical PT60M payloads, as tested below, but this
manifest does not schedule monthly/final settlement retrieval or old-history backfill.

## Evidence and fixtures

A bounded live read through `energyctl record-fixture --live`, on 2026-09-23 for version 0 on
2026-09-21, returned HTTP 200 and 96 PT15M items. Payload SHA-256:
`a6a5ecdb62b7d54935dedb4c840b8e30fcc09e56f1a9e6182ea3d7ab695e7378`.
The response envelope and item fields match the admission. The real capture is local evidence
outside the repository. This verifies the request and shape, not a publication SLA.

[OTE Terms of Use](https://www.ote-cr.cz/en/documentation/term-of-use) require written consent
for reproduction (recorded in docs/06 §1.4); redistribution permission remains unconfirmed.
Every committed fixture is **synthetic** XML with the observed SOAP envelope/field names and
invented values, wrapped by `energyctl record-fixture --from-file` as a Bronze blob plus capture
entry. Capture timestamps are synthetic and independent of the document's delivery date.

| Fixture | Demonstrates | Expected outcome |
|---|---|---|
| `ordinary_day` | 2026-09-21, 96 periods; all ignored fields including optional Emerg | 288 rows; complete partition event |
| `spring_dst` | 2026-03-29, 92 periods; 01:45 CET → 03:00 CEST | 276 rows; complete partition event |
| `autumn_dst` | 2025-10-26, 100 periods; two distinct 02:00 offsets | 300 rows; complete partition event |
| `monthly_version` | 2026-08-01, response Version 1 | 288 rows with version 1 |
| `final_version` | Same day/periods, response Version 2 | 288 rows with version 2 |
| `historical_hourly` | 2024-06-30, 24 PT60M periods | 72 rows preserving PT60M |
| `edge_values` | Negative decimals, published zero, absent elements for all three metrics | 9 rows including 3 NULLs; incomplete partition event |
| `empty` | Empty Result, not yet published | 0 rows |
| `soap_fault` | SOAP Fault carried by an HTTP-200 Bronze entry | Quarantine containing `SOAP Fault` |

Goldens were authored independently from the fixture XML: counts are periods × 3, decimal
strings are read directly, and boundary/DST offsets were calculated by hand. The goldens
explicitly check the response version. No expected value was copied from platform output.
Human golden sign-off remains the Route A reviewer gate (ADR-022).

```sh
uv run python -m energy_platform.cli validate ote_imbalance_settlement
uv run python -m energy_platform.cli run-target-tests ote_imbalance_settlement
make check
make pr-surface BASE=main
```
