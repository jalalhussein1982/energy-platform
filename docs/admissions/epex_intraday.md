# Admission request — `epex_intraday` (2026-09-20)

> **Negative demo (03 Phase 4; ADR-022 §2; 05 C-54).** This request was produced by
> `energyctl new-target epex_intraday --modality html-table --host www.epexspot.com` in a scratch
> targets root, `energyctl validate` (`ADMISSION_REQUIRED`, exit 2) and `energyctl admission-request`.
> It is the *correct* stopping point for a restricted source: no directory under `targets/`, no
> registry edit, no invented unit, no live read. The maintainer's expected answer is **refuse**
> (01 §2: exchange pages are class C — licensed data; 01 §10 admission register). The Phase 5
> CronJob renderer additionally refuses any manifest whose `license` starts with `restricted`.

| | |
|---|---|
| Route | **B — source admission** (ADR-022 §1). This file is the whole PR; the registry change it asks for is a maintainer's platform PR under CODEOWNERS. |
| `energyctl validate epex_intraday` | `ADMISSION_REQUIRED` |
| Proposed `dataset_id` | `epex.idm_continuous` |
| Unregistered datasets | `epex.idm_continuous` |
| Unregistered metrics | `epex.idm_continuous.price_vwap`, `epex.idm_continuous.volume_total` |
| Unregistered hosts | `www.epexspot.com` |
| Hosts needing `allow_insecure` | none |

## Validation errors (registered but inconsistent, if any)

- none

## Source

| | |
|---|---|
| Endpoint / modality | html-table on `www.epexspot.com` |
| License / terms | restricted: EPEX SPOT market data is licensed; the public web page may not be scraped or redistributed without a data licence (docs/01-data-scope.md §2, §10; ADR-008) — https://www.epexspot.com/en/legal |
| Redistribution of raw captures confirmed? | No — and not requested: EPEX SPOT market data is licensed (01 §2 class C); the page was **not read** (01 §10) |
| Publication cadence and latency observed | Not observed — no poll was made, deliberately (01 §5) |

## Proposed contract (01 §6.3 / §9 — the maintainer decides; nothing here is a registry edit)

| Item | Proposal |
|---|---|
| Identity key | `(bidding_zone, delivery_start_utc, resolution)` — the same business observation as `ote.idm_continuous`; a second source for it would need 01 §3-style reconciliation rules, not a new dataset |
| Fixed / constrained dimensions | `bidding_zone = CZ` |
| Resolutions | `PT15M` (unverified — not read) |
| Revision marker (`source_version`) | none known (not read) |

| Metric (as declared in the manifest) | Unit | Sign | Separator |
|---|---|---|---|
| `price_vwap` | `EUR/MWh` | as_published | dot |
| `volume_total` | `MWh` | as_published | dot |

For each metric the maintainer needs: unit **as published**, sign rule (`negative_allowed`,
`non_negative`, `non_negative_expected`), what NULL means, currency if any, and which transport
is the system of record when several deliver it.

## Sample shape

None — no response was fetched. The column names in the manifest (`Weighted Avg. Price`, `Volume`,
`Period`) are placeholders of the demo, not observed headers; a real request would carry a bounded
excerpt here. A restricted source gets no fixture at all.

## What the requester will do once admitted

Nothing is expected: the request exists to show the refusal path. Were the maintainer to obtain a
data licence, the route would be a 01 §3-style contract, a §10 row, registry entries under
CODEOWNERS, and only then a Route A PR touching `targets/epex_intraday/`.
