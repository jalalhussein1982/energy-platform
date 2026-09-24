# Admission — `ote_imbalance_settlement` (2026-09-23) — **ADMITTED**

> **Held-out source (ADR-022 §3; plan P6-D1).** Admitted by the maintainer through Route B so
> that Phase 7 run 1 can add its adapter blind: the contract and the admission row exist, the
> adapter does not. `targets/ote_imbalance_settlement/` must not exist before Phase 7.

| | |
|---|---|
| Route | **B — source admission** (ADR-022 §1), decided by the maintainer (@jalalhussein1982) |
| Decision | **Admit** `ote.imbalance_settlement` 1.0.0 with the three metrics below; nothing else from the response |
| Registry change | `energy_platform/contracts/registry.py` (`_OTE_IMBALANCE_SETTLEMENT`), CODEOWNERS path |
| Host | `www.ote-cr.cz` — already registered (T1/T2/E1); no host registry change |
| Admission row | `01-data-scope.md` §10 |
| Evidence | `06-source-verification.md` §9 (WSDL + two bounded reads, hashes) |
| `energyctl validate` on a scratch manifest | `OK` (was `ADMISSION_REQUIRED` before this change) |

## Source

| | |
|---|---|
| Endpoint / modality | SOAP 1.1, `https://www.ote-cr.cz/pw-data/services/PublicDataService`, action `http://www.ote-cr.cz/schema/service/public/GetImbalanceSettlementPeriodE` |
| Request | `Version` (0 daily, 1 monthly, 2 final monthly settlement), `StartDate`, `EndDate`, optional `StartPeriod` / `EndPeriod` |
| License / terms | OTE Terms of Use — https://www.ote-cr.cz/en/documentation/term-of-use (same as T1) |
| Redistribution of raw captures confirmed? | **Refused** — OTE market desk 2026-09-24: internal use only, must not be published to third parties (06 §1.4); repository fixtures are synthetic with the real shape, permanently (01 §10) |
| Publication cadence and latency observed | Not observed; no figure is quoted (the polling campaign was closed as not run, 2026-09-23) |

## Contract (decided)

| Item | Decision |
|---|---|
| `dataset_id` / `source_id` | `ote.imbalance_settlement` / `ote` |
| Identity key | `(bidding_zone, delivery_start_utc, resolution, version)` |
| Fixed dimensions | `bidding_zone = CZ` |
| `version` | ← the envelope `source_version`, i.e. the response field `Version` (`0`, `1`, `2`); each settlement version is its own identity (04 §2) |
| Resolutions | `PT15M` (from 2024-07-01, 01 §2 S08), `PT60M` before |
| Time | `Date` + `PeriodIndex` + `PeriodResolution`, Europe/Prague, as T1 (period index → local interval → UTC; 92/96/100 by the calendar) |

| Metric | Source field | Unit | Currency | Sign rule | NULL means |
|---|---|---|---|---|---|
| `system_imbalance` | `SystemImbalance` | MWh | — | `negative_allowed` (published as is; meaning of the sign [UNVERIFIED]) | not yet published for this settlement version |
| `imbalance_price` | `SettlImbalancePrice` | CZK/MWh | CZK | `negative_allowed` | as above |
| `counter_imbalance_price` | `SettlCounterImbalancePrice` | CZK/MWh | CZK | `negative_allowed` | as above |

A published `0.000` is a value, not an absence (06 §9: up to 41 of 96 periods). The other
response fields (`Sum`, `PositiveImbalance`, `NegativeImbalance`, `RoundedImbalance`, `ReCost`,
`ImbalanceCost`, `PriceWARE`, `PriceRE`, `PriceWAIM`, `PriceCurve`, `Emerg`) are **not admitted**:
an adapter lists them in `mapping.ignore_fields` (ADR-034), never maps them.

## Sample shape (one item, bounded)

```text
<Item><Version>0</Version><Date>2026-09-21</Date><PeriodResolution>PT15M</PeriodResolution>
<PeriodIndex>1</PeriodIndex><SystemImbalance>0.65683</SystemImbalance>…
<SettlImbalancePrice>0.000</SettlImbalancePrice><SettlCounterImbalancePrice>0.000</SettlCounterImbalancePrice>…</Item>
```

## What happens next

Phase 7 run 1: a fresh session, given only `README.md`, `docs/08-adding-a-target.md` and the
endpoint above, opens a Route A PR touching only `targets/ote_imbalance_settlement/`.
