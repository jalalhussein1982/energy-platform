# ote_dam — E1, OTE day-ahead market (SOAP `GetDamPricePeriodE`)

The **adapter-addition demo** (03 Phase 4; ADR-022 Route A): added last, entirely through the MCP
contributor workflow (`energyctl mcp-serve`, ADR-007) — `scaffold_target` → `write_target_file` →
`record_fixture` (offline payloads) → `validate_target` → `run_target_tests` → `open_pr`. The
session's refusals (a write outside the surface, a forbidden construct, a live fetch without
`--allow-network`) are recorded in `docs/06-source-verification.md` §5. No platform file changed.

Contract: `docs/01-data-scope.md` §3 E1. Endpoint as T1; the request needs `PeriodResolution`;
the response item adds `PeriodInterval`, `HourlyPrice`, `VolumeTotal`, `EmergencyState` (WSDL and
live reads of 2026-09-20: `docs/06` §5, evidence rows 1, 10, 11). Four registered metrics of
`ote.dam`: `price`, `price_hourly` (constant across the hour's four quarters), `volume_total`,
`emergency_state` (dimensionless flag, unit `1`, NULL when the element is absent — every live item).

## Day-ahead timing

Results for delivery day D are published on D-1 (complete by 14:24 CEST in the live read). The
manifest polls hourly from 12:00 on D-1 and asks for `{next_delivery_day}` (ADR-033 §4); the
observations carry the document's own `Date`, so Silver and completeness see D.

## Fixtures (synthetic copies of the live shape — 01 §10)

| Fixture | Demonstrates | Expected outcome (golden) |
|---|---|---|
| `ordinary_day` | 96 PT15M items for 2026-09-21, `EmergencyState` absent | 384 rows (96 × 4, the flag NULL), `complete 96/96` |
| `hourly_day` | 24 PT60M items, `PeriodInterval` `00-01`, `Price` = `HourlyPrice` | 96 rows at PT60M |
| `spring_dst_day` | 92 items on 2026-03-29 | 368 rows, `complete 92/92` |
| `autumn_dst_day` | 100 items on 2025-10-26 | 400 rows, `complete 100/100` |
| `negative_price` | `Price` −0.05 and `EmergencyState` 1 on one item | kept as published; flag `1` |
| `no_result` | empty `<Result/>` before publication | 0 rows, no event |
| `soap_fault` | SOAP Fault over HTTP 200 | quarantine `SOAP Fault` |

Values are deterministic formulas; check any golden row with `grep '<PeriodIndex>N<' fixtures/<name>/blob`.
Live payloads are not committed (06 §1.4).

## Checks

```text
energyctl validate ote_dam
energyctl run-target-tests ote_dam
make check
energyctl pr-bundle ote_dam
```
