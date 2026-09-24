# Step 1 — What data do we intend to collect?

**Status: closed (v1.0, 2026-09-19).** This is the agreed data scope that Step 2 (architecture, HA, IaC, agent guardrails) builds on.

Task context: ČEZ Group take-home assignment — "high availability data engineering scraping and
processing system for intraday energy data, with deployments and infra as code, so that new
public-data scraping targets can be added easily even by someone else."

This document answers the first question only: **what public intraday energy data the system
collects, from exactly which sources, under which contracts.** Architecture, HA, IaC and agent
guardrails are Step 2; section 11 lists what Step 2 must prove.

**Review history.** v0.1 was a research catalogue. It went through one round of independent
agent review (13 findings, `message-board/`), and every finding was either accepted or answered
with primary evidence: live, anonymous, single-request reads of each source, saved with hashes.
v1.0 replaces obsolete documentation with operation-level contracts, labels every claim as fact,
inference or [UNVERIFIED], defines access classes, reduces the MVP to three anonymous targets plus
one adapter-addition demo, and specifies identity, time, revision and value semantics. Evidence
ledgers: `message-board/evidence/SOURCES.md` (S01–S09) and
`message-board/evidence/SOURCES-round-2.md` (S10–S17).

**What remains open, by design.** Exact publication latencies need a polling campaign, which is a
Step 2 deliverable. ENTSO-E is untested and optional. Written reuse confirmation from OTE and ČEPS
has not been sought; the repository ships synthetic fixtures until it is. None of these change the
scope.

---

## 1. Company context: facts, hypotheses, design choice

**Confirmed from ČEZ's own pages (S01):** ČEZ generates from nuclear, coal, gas, hydro including
pumped storage, solar, wind and biomass; plans a fourth pumped-storage plant at Orlík; runs a
Prague trading desk active on OTE, OKTE, EEX/EPEX, PXE, TGE, HUPX, CEGH and OTC; publishes REMIT
fundamental data via EEX; created the ČEZ Energy customer subsidiary in 2026; and sells a
home-battery flexibility product.

**Confirmed from OTE (S08):** Czech imbalance settlement moved to 15 minutes on 1 July 2024,
15-minute cross-border intraday products started the same day, and the day-ahead market moved to a
15-minute market time unit for delivery from 1 October 2025.

**Hypothesis, not fact:** that the hiring team's consumer is a trading or flexibility desk, and
that public aggregate feeds are suitable for any dispatch or settlement decision. Nothing public
establishes the team's real consumer, SLA or internal systems.

**Design choice for this assignment:** build an *intraday market monitoring and research
pipeline* for the Czech bidding zone. It collects public, aggregate, already-published results
and physical-system observations. It is explicitly **not** a low-latency trading feed, and no
freshness promise in this document should be read as suitable for automated execution.

---

## 2. Access classes and policy

| Class | Definition | Policy |
|---|---|---|
| A — anonymous public | No account, no token, documented for automated access | Allowed. All MVP targets are class A. |
| B — publicly obtainable with registration or token | Free, but needs an account or an emailed access request (ENTSO-E) | Allowed as an optional, disabled-by-default adapter. The reproducible demo must run without it. Tokens live only in secret injection, never in fixtures, URLs, logs, IaC state or repository history. |
| C — restricted or licensed | Participant portals, paid data, order books | Excluded. |

Robots rules, terms of use and fixture redistribution are handled per target in section 9. An
HTTP 200 never implies permission.

---

## 3. Committed MVP targets (exact contracts)

Three targets, all class A, all Czech bidding zone, plus one adapter-addition demo. Everything
else in this document is a candidate (section 4), not a deliverable.

### T1 — OTE continuous intraday market, SOAP (system of record for price and volume)

| Item | Value | Evidence |
|---|---|---|
| Endpoint | `https://www.ote-cr.cz/pw-data/services/PublicDataService` (SOAP 1.1; WSDL at `?wsdl`) | S04 live, S10 doc (new URL since 31 March 2026) |
| Operation | `GetImPricePeriodE`, SOAPAction `http://www.ote-cr.cz/schema/service/public/GetImPricePeriodE` | S04 live |
| Request | `StartDate`, `EndDate` (YYYY-MM-DD, delivery days); optional `StartPeriod`, `EndPeriod` (1–100 for PT15M) | WSDL + S10 |
| Limits | More than 31 delivery days → only 31 returned from `StartDate`. Legacy `GetImPriceE` stops at delivery 30 June 2024. | S10 doc |
| Response item | `Date`, `PeriodResolution` (PT15M or PT60M, the day's smallest resolution), `PeriodIndex`, optional `Emerg`, optional `Price`, optional `Volume` | WSDL, S04 |
| Meaning | `Price` = volume-weighted average price of standard 15-min and 60-min intraday contracts for the period; `Volume` = traded volume | S10 doc |
| Units | `Price` EUR/MWh with 2 decimals; `Volume` MWh with 3 decimals; `Emerg` = 1 when a state of emergency was declared; decimal separator is a dot | S17 doc (manual, response table) |
| Not provided | Buy/sell split, min, max, last price, any publication timestamp | WSDL |
| Live sample | 2026-09-17 periods 1–3: 170.13 / 170.21 / 170.54 EUR/MWh; 125.275 / 126.025 / 129.550 MWh | S04 |
| Publication cadence | Results for a quarter-hour appear around its gate closure, i.e. before or at delivery start; at most 15 minutes between fills. Two observations on the XLSX of the same dataset (S17); exact latency to be measured in Step 2. | S17 live, partial |
| Historical coverage | Period-based operation is documented from 1 July 2024. Earlier dates via the legacy hourly operation are a separate, hourly-native dataset. Full coverage not tested. | S10; [UNVERIFIED] |

### T2 — OTE continuous intraday market, daily XLSX (supplies the richer metrics)

| Item | Value | Evidence |
|---|---|---|
| Discovery | Primary: fetch `https://www.ote-cr.cz/en/short-term-markets/electricity/intra-day-market` and read the `.xlsx` link from the HTML. Fallback: `https://www.ote-cr.cz/pubweb/attachments/27/{YYYY}/month{MM}/day{DD}/IM_15MIN_{DD}_{MM}_{YYYY}_EN.xlsx`, confirmed for four dates across 2025–2026. | S13, S17 live |
| Layout | Title in row 3; header in row 6; periods 1–96 in rows 7–102; footer note in row 103 | S13 fixture check |
| Columns | Period; Time interval (`HH:MM-HH:MM`, local); Traded volume (MWh); Traded volume – purchase (MWh); Traded volume – sold (MWh); Average price (EUR/MWh); Minimal price (EUR/MWh); Maximal price (EUR/MWh); Last price (EUR/MWh) | S13 |
| Numeric storage | Cells are numeric in the XLSX. The decimal comma seen on the HTML page (S02) is a rendering artefact; the parser must still accept both. | S13, S02 |
| Completeness | 2026-09-19 file: 8 periods populated at about 02:00 local, 10 at about 02:20 local. 2026-09-18 file: all 96 populated by 02:20 local the next day. The daily-named file is filled during the delivery day and is complete shortly after it. | S13, S17 (three observations) |
| Row count | 96 rows on an ordinary day; 92 on the spring DST day (2026-03-29) with a bridging label `01:45-03:00`; 100 on the autumn DST day (2025-10-26) with repeated `02:xx` labels. The `Time interval` label is display only; the parser keys on `Period`. | S17 live |

**Reconciliation between T1 and T2.** Both describe the same business observation (OTE continuous
intraday, CZ, one delivery period). Rules:

1. Each transport is stored as its own source document with its own `raw_ref` and `source_transport`.
2. `price_vwap` and `volume_total` may arrive from both. T1 is the system of record for those two metrics; T2's copies are stored, and a difference above a tolerance of 0.01 EUR/MWh or 0.001 MWh is flagged as a `reconciliation_mismatch` quality event, never silently merged.
3. `volume_buy`, `volume_sell`, `price_min`, `price_max`, `price_last` exist only in T2. If T2 is unavailable those metrics are **absent**, and the target's status says so. T1 is not a fallback for them.
4. An observation is complete for a delivery period only when the declared metric set for the period is present from its owning transport.

### T3 — ČEPS transmission-system load, SOAP

| Item | Value | Evidence |
|---|---|---|
| Endpoint | `https://www.ceps.cz/_layouts/CepsData.asmx` (SOAP 1.1 and 1.2; WSDL at `?WSDL`). The WSDL's own address points at an Azure host; the ceps.cz path is used and worked. | S14 live |
| Operation | `Load`, SOAPAction `https://www.ceps.cz/CepsData/Load` | S14 |
| Request | `dateFrom`, `dateTo` (`xs:dateTime`, local Prague clock, `dateTo` inclusive); `agregation` from `DataAgregation` (QH, HR, DY, WE, MO, YR and peak/off-peak variants); `function` (AVG observed; other values [UNVERIFIED]); `version` from `DataVersion` (RT = real data; DF/DR daily forecast/revision; IDF intraday forecast; weekly, monthly, quarterly, yearly forecast/revision) | S14 |
| Response | `information` block echoing the request; `series` with `value1` = "Load including pumping [MW]" and `value2` = "Load [MW]"; `data/item` with `@date` carrying the local UTC offset (`+02:00`) and one attribute per series | S14 |
| Live sample | 2026-09-17 00:00–01:00, QH, AVG, RT: 6382.4, 6279.867, 6311.533, 6349.733, 6390.267 MW | S14 |
| Not provided | Publication timestamp, revision marker | S14 |
| Cadence, latency, history | [UNVERIFIED]. Portal offers years from 2010, which is a UI range, not proof of series coverage. | S05 |
| Access note | `ceps.cz/robots.txt` disallows all crawling. HTML scraping of ceps.cz is therefore excluded; only the documented web service is a candidate route, subject to section 9. | S15 |

Point-versus-interval: with `function=AVG` and `agregation=QH` each item is the average over the
quarter-hour beginning at `@date`. Other `function` values and the non-RT `version` semantics are
[UNVERIFIED]; the ČEPS interface description DOCX sits behind a JavaScript-rendered page and was
not parsed. The MVP uses AVG and RT only, which are live-verified.

### E1 — Adapter-addition demo: OTE day-ahead market, SOAP

Used to demonstrate the contributor workflow (new target through the scaffold, no core edits).
Same endpoint as T1. Operation `GetDamPricePeriodE`; request adds a required `PeriodResolution`;
response item adds `PeriodInterval` (`HH:MM-HH:MM`), `HourlyPrice`, `VolumeTotal`,
`EmergencyState`. Live sample 2026-09-17 periods 1–3: 199.96 / 187.00 / 177.24 EUR/MWh with
hourly price 183.98 (S11). **OTE**, not PXE, operates this service; PXE's site mirrors the
common day-ahead market and is not a second contract.

---

## 4. Candidate catalogue (not committed)

Candidates keep their evidence label. Promotion to a target requires a section 3 style contract,
a bounded live read, and a section 9 entry.

| Candidate | Source / route | Class | What is known | Label |
|---|---|---|---|---|
| Imbalance settlement, CZ | OTE `GetImbalanceSettlementPeriodE`, `Version` 0 daily / 1 monthly / 2 final monthly | A | Contract confirmed live; prices in Kč/MWh; monthly version for 15 Sep 2026 was empty (not yet published) while 1 Aug 2026 was populated | verified shape, cadence [UNVERIFIED] (S10, S12) |
| Estimated imbalance price and current system imbalance, CZ | ČEPS `OdhadovanaCenaOdchylky`, `AktualniSystemovaOdchylkaCR` | A | Operations exist in the WSDL; not called | [UNVERIFIED] (S14) |
| Generation, generation RES, cross-border flows, frequency, balancing activation | ČEPS operations of the same names | A | Operations exist; `Generation`/`GenerationRES` take an extra `para1` | [UNVERIFIED] (S14) |
| Intraday auctions (IDA), CZ | OTE `GetIDAAllPeriodE` with required `Auction` identifier, optional `InEur` | A | Contract in WSDL; not called | [UNVERIFIED] |
| Day-ahead prices, load, generation, forecasts, cross-zonal capacity for CZ and neighbours | ENTSO-E Transparency REST | B | Token required after registration and emailed request (S07). No call made. Coverage, limits, cadence unknown here. | [UNVERIFIED] |
| Neighbouring exchange intraday indices (EPEX, OKTE, TGE, HUPX) | Public HTML/CSV pages | A or C | Not examined; terms unknown | [UNVERIFIED] |
| REMIT urgent market messages | EEX transparency / ENTSO-E outages | A/B | Event-shaped data; needs its own contract (section 6) | deferred |
| Czech intraday gas, EUA prices, weather, hydrology | OTE gas operations, EEX pages, Open-Meteo, ČHMÚ | A | Not examined | [UNVERIFIED] |

---

## 5. Freshness contract

Freshness is measured against **expected publication**, not against a successful fetch.

Definitions per target and delivery partition (a delivery day for T1/T2, a delivery hour for T3):

- **pending**: expected publication time not reached.
- **partial**: some periods present, others absent; normal for T1/T2 during the delivery day.
- **late**: expected publication time passed and the partition is still not complete.
- **complete**: every expected period has its owning-transport metrics; for T1/T2 the expected count is the day's quarter-hour count (96, 92 or 100).
- **stale fetch**: HTTP 200 whose payload hash equals the previous fetch. Counted as a successful poll, never as new data.

Per target:

| Target | Delivery resolution | Expected publication | Poll interval (initial) | Correction window | Observed |
|---|---|---|---|---|---|
| T1 | PT15M (PT60M before July 2024) | Around each period's gate closure (S17, via the XLSX of the same dataset) | 15 min during the delivery day, hourly for D-1..D-3 | 3 days [assumption] | one SOAP read; fill behaviour inferred from T2 |
| T2 | PT15M | Around each period's gate closure; complete shortly after the day ends (S17) | 15 min | as T1 | three reads: 8/96 at 02:00, 10/96 at 02:20, D-1 complete |
| T3 | PT15M (QH) | [UNVERIFIED] | 15 min | 1 day [assumption] | one read for D-2 |
| E1 | PT15M | Once after the day-ahead auction [UNVERIFIED] | hourly from 12:00 CET on D-1 | 1 day | one read |

**Source outage versus ingestion outage.** A poll that fails at the network/HTTP layer is an
ingestion observation. A poll that succeeds but returns an empty or unchanged payload after the
expected publication time is a source-lateness observation. They are separate status fields and
separate alerts. HA replicas fix the first; nothing in this system fixes the second.

A short observation exercise (one week of polls per target) is a Step 2 deliverable before any
latency figure is quoted.

---

## 6. Data model: envelope plus typed dataset contracts

The generic part is the **provenance and time envelope**. The dataset-specific part is a typed
contract with a declared identity key. A new adapter registers a contract; it cannot invent
dimensions, units or metric names outside the registry.

### 6.1 Envelope (all datasets)

```
source_id          ote | ceps | ...                       registered
dataset_id         ote.idm_continuous | ote.dam | ceps.load | ...   registered
source_transport   soap | xlsx | html | rest              registered
contract_version   semver of the dataset contract used to parse
raw_ref            immutable object-store key of the raw response/file
payload_sha256     hash of the raw payload
fetched_at         UTC instant of the fetch (always present)
source_published_at UTC instant stated by the source, or NULL when the source gives none
source_version     source-supplied version/revision/status, or NULL (e.g. OTE settlement 0/1/2, ČEPS RT/DF/IDF)
processed_at       UTC instant of parsing
```

### 6.2 Time fields (all interval datasets)

```
delivery_start_utc   UTC, start-inclusive
delivery_end_utc     UTC, end-exclusive
resolution           ISO 8601 duration as declared by the source: PT15M, PT60M, PT1M ...
local_date           source civil date (Europe/Prague) used for period indices
period_index         source index within local_date, when the source uses one
kind                 interval | point
```

### 6.3 Typed contracts and identity keys

| dataset_id | Identity key (business key) | Metrics (unit) |
|---|---|---|
| `ote.idm_continuous` | (bidding_zone=CZ, delivery_start_utc, resolution) | price_vwap (EUR/MWh), volume_total (MWh) from T1; volume_buy, volume_sell (MWh), price_min, price_max, price_last (EUR/MWh) from T2 |
| `ote.dam` | (bidding_zone=CZ, delivery_start_utc, resolution) | price (EUR/MWh), price_hourly (EUR/MWh), volume_total (MWh), emergency_state |
| `ceps.load` | (area=CZ, delivery_start_utc, resolution, aggregation_function, version) | load_incl_pumping (MW), load (MW) |
| `ote.imbalance_settlement` (candidate) | (area=CZ, delivery_start_utc, resolution, settlement_version) | system_imbalance (MWh), settlement_price (CZK/MWh), ... |
| `ote.ida` (candidate) | (bidding_zone=CZ, auction_id, delivery_start_utc, resolution) | price, volume, import, export, net (EUR/MWh or CZK/MWh per `InEur`) |
| `ceps.crossborder_flows` (candidate) | (from_area, to_area, delivery_start_utc, resolution, aggregation_function, version) | flow (MW) |
| `ceps.generation` (candidate) | (area=CZ, generation_type, delivery_start_utc, resolution, aggregation_function, version) | generation (MW) |
| forecasts (candidate) | (... , forecast_issued_at or run_id) | value |

Identity examples that stay distinct on one delivery interval: flows CZ→DE-LU and CZ→AT differ
in (from_area, to_area); nuclear and solar differ in generation_type; IDA1 and IDA2 differ in
auction_id; ČEPS RT and IDF differ in version.

**Product duration versus reported resolution.** T1/T2 report every quarter-hour at PT15M even
though hourly contracts are traded; the source aggregates them into its smallest resolution
(S10). The stored resolution is the reported one. Product duration is not recoverable from these
feeds and is not claimed.

**Event-shaped data** (REMIT messages, outages) needs an event contract with message id, asset,
status and revision. It is deferred and not forced into the interval model.

---

## 7. Time contract

- Store UTC; keep the source's civil date and period index alongside.
- Sources follow Europe/Prague civil time. Conversion goes **period index → local interval →
  UTC**, never by attaching a timezone to an ambiguous local label. This is not theoretical: the
  autumn XLSX repeats `02:00-02:15`-style labels for the second 02:00 hour, and the spring XLSX
  carries a bridging label `01:45-03:00` (S17). Expected quarter-hours per local day: 96, 92
  (spring), 100 (autumn); the count is computed from the calendar, never hard-coded.
- ČEPS timestamps carry an explicit offset (S14) and are parsed offset-aware.
- Intervals are start-inclusive, end-exclusive. `function=AVG` samples from ČEPS are intervals;
  a future 1-minute frequency series would be `kind=point`.
- Native resolution is preserved. Hourly historical intraday data (before July 2024) stays
  PT60M. Resampling is a separate derived dataset with metric-specific rules: prices are
  volume-weighted, energies are summed, powers are averaged. One hourly price never becomes four
  fabricated quarter-hour observations.

Fixtures required before merge: ordinary day, 23-hour day, 25-hour day, native hourly sample,
and a partially filled day. Real examples of the first three and the last already exist in
`message-board/evidence/` (2026-09-18, 2026-03-29, 2025-10-26, 2026-09-19); repository fixtures
are synthetic copies of their shape (section 10).

---

## 8. Revisions, deduplication and replay

- **Observation identity** is the identity key from section 6.3 plus `source_version`.
- **Version identity** is (observation identity, payload_sha256 of the source document).
- `source_published_at` may be NULL. It is never filled from `fetched_at`. Ordering of
  versions uses `source_published_at` when present, otherwise `fetched_at`, and the ordering
  basis is recorded.
- **Unchanged retry**: same payload hash → one new fetch log entry, no new version, no new
  business observation.
- **Changed payload, same or absent publication time** → new version, auditable, with the diff
  attributable to the raw documents.
- **Older arrival after newer**: versions are appended, never overwritten; the *current* view
  selects by the recorded ordering basis, so a late replay of an old document does not become
  current.
- **Parser replay** (same raw document, new contract_version) produces rows tagged with the new
  contract_version and is distinguishable from a provider correction (new raw document).
- **Cross-source estimates** (ČEPS estimated imbalance price) and **OTE settlement versions**
  (0/1/2) are different datasets or different `source_version` values. They coexist; no rule
  overwrites one with the other. A "preferred" view is a documented query, not a mutation.
- Raw documents are immutable and retained; every derived row points to one.

---

## 9. Value semantics and validation

Per-metric registry (illustrative rows; the registry is the contract, not this table):

| Metric | Unit | Currency | Sign | Null meaning | Notes |
|---|---|---|---|---|---|
| price_vwap, price_min, price_max, price_last (IDM) | EUR/MWh | EUR | negative allowed | no trade in period, or not yet published | decimal-safe parsing, 2 dp observed |
| volume_total, volume_buy, volume_sell (IDM) | MWh | — | ≥ 0 | not yet published | 3 dp observed; no assumption that buy = sell = total |
| price, price_hourly (DAM) | EUR/MWh | EUR | negative allowed | no result | — |
| load, load_incl_pumping (ČEPS) | MW | — | ≥ 0 expected, not enforced | missing sample | power, not energy |
| settlement prices (candidate) | CZK/MWh | CZK | negative allowed | not yet settled for that version | source label Kč/MWh; no silent FX conversion |

Rules: preserve native currency; any conversion is a derived value with FX source and date.
Blank cells and absent elements become NULL, never zero. Non-finite values, unknown columns,
changed header text, unit label changes and currency mismatches quarantine the whole document
with a reason; nothing is coerced. MW versus MWh is checked against the registry, not inferred.

Fixtures required: negative and zero prices, absent `Price`, empty `<Result/>`, decimal comma
string, extra column, changed unit header.

---

## 10. Source admission register

| Target | Terms reviewed | robots.txt | Automated access documented by the source | Fixture policy | Open items |
|---|---|---|---|---|---|
| T1/E1 OTE SOAP | OTE Terms of Use (S09) read on 2026-09-19: copying restrictions, no availability guarantee | allowed (S15) | Yes, public web-service manual (S10) | Repository fixtures are **synthetic** with the real shape, **permanently**: OTE answered 2026-09-24 that the data is for internal use only and must not be published to third parties (06 §1.4); saved live samples stay in local evidence | None on terms. Cadence decided 2026-09-24 (ADR-033 amendment 3): E1 four reads after 13:05, corrections once a day |
| T2 OTE XLSX | as above | allowed | Results page is public; no API statement for the file | synthetic, permanently (as above) | OTE named a daily summary or a read after each 15-minute contract closes; the 15-minute poll is the latter; correction re-reads once a day (ADR-033 amendment 3) |
| T3 ČEPS SOAP | Not published beyond the interface description v3.2 (S06, 06 §4.5); letter sent 2026-09-24, unanswered; **maintainer decision 2026-09-24**: internal use only, no redistribution, the documented service only | **disallows all crawling** (S15) — read as the website; the web service is documented for structured data delivery and is the only thing called | Yes, "structured data delivery" interface with test client | synthetic, permanently (06 §4.5) | None on terms (a ČEPS reply can only loosen the decision). `value1` = `value2` on every QH item stays a question for ČEPS (06 §4.2) |
| ENTSO-E (candidate) | Not reviewed | n/a | REST with token (S07) | none until admitted | registration, terms, redistribution |
| OTE imbalance settlement (held-out, admitted 2026-09-23 via Route B, ADR-022 §3; no adapter until Phase 7) | OTE Terms of Use (S09), as T1 | allowed (S15) | Yes, public web-service manual (S10), operation `GetImbalanceSettlementPeriodE` | synthetic with the real shape, permanently, as T1 | as T1; imbalance sign meaning and version timing [UNVERIFIED] (06 §9; the timing question was not in the sent letter) |
| Exchange pages (candidate) | Not reviewed | unknown | unknown | none | everything |

Policy changes to this register need maintainer review. No agent or contributor may add a target
without a row here.

---

## 11. Not collected, and hand-off to Step 2

Not collected: class C sources; personal or customer data; anything obtained by circumventing
access controls, captchas or rate limits; HTML from ceps.cz.

Step 2 must specify and later demonstrate (R12): failure domains for scheduler, workers, queue
and storage with idempotent at-least-once processing; measurable availability, freshness, RPO
and RTO with failure tests; clean-environment IaC with pinned images, migrations, secret injection,
teardown and restore; an adapter scaffold with a narrow edit surface and human-reviewed golden
fixtures; protected CI and approvals for schemas, policy, dependencies and infrastructure;
least-privilege runtime credentials and bounded egress; scraped content treated as untrusted text;
and a rejected bad merge request as a demonstration. Multiple containers on one host are not
host-level HA and will be labelled as a simulation if that is what is delivered.

---

## 12. Claim ledger

| Claim | Level | Evidence |
|---|---|---|
| OTE public SOAP endpoint, anonymous, current | live | S04, S10, S11, S12 |
| `GetImPricePeriodE` fields, units and limits | live + doc | S04, S10, S17 |
| XLSX columns, URL pattern, DST layouts, rolling fill | live + fixture | S13, S17 |
| ČEPS SOAP endpoint, anonymous, `Load` shape, enums | live | S14 |
| ČEPS robots disallow | live | S15 |
| Settlement Version 0/1/2 and Kč/MWh | doc + live | S10, S12 |
| 15-minute market transitions | doc | S08 |
| ČEZ business context | doc | S01 |
| Fill cadence of intraday results (≤ 15 min, around gate closure) | live, 2 observations | S17 |
| Exact publication latency per target | — | [UNVERIFIED], Step 2 polling campaign |
| Any ENTSO-E coverage or limit | — | [UNVERIFIED] |
| Historical coverage of any series | — | [UNVERIFIED] |

---

## Sources consulted

- ČEZ Group home: https://www.cez.cz/nextcez/en/home
- ČEZ Trading: https://www.cez.cz/en/cez-group/cez/trading
- OTE public web-services manual, revision 13 April 2026: https://www.ote-cr.cz/cs/dokumentace/xsd-wsdl-manual-pubweb/cs/dokumentace/xsd-wsdl-manual-pubweb/uzivatelsky-manual_webove_sluzby_ote_k.pdf
- OTE documentation landing page: https://www.ote-cr.cz/cs/dokumentace/xsd-wsdl-manual-pubweb
- OTE PublicDataService WSDL: https://www.ote-cr.cz/pw-data/services/PublicDataService?wsdl
- OTE continuous intraday results: https://www.ote-cr.cz/en/short-term-markets/electricity/intra-day-market
- OTE 15-minute transition: https://www.ote-cr.cz/en/documentation/electricity-documentation/information-to-switch-to-15-min-interval
- OTE Terms of Use: https://www.ote-cr.cz/en/documentation/term-of-use
- OTE intraday XLSX example: https://www.ote-cr.cz/pubweb/attachments/27/2026/month09/day19/IM_15MIN_19_09_2026_EN.xlsx
- ČEPS all data: https://www.ceps.cz/en/all-data · ČEPS web services: https://www.ceps.cz/en/web-services · ČEPS WSDL: https://www.ceps.cz/_layouts/CepsData.asmx?WSDL
- ENTSO-E token guidance: https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188-How-to-get-security-token
