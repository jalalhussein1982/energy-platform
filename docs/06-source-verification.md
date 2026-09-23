# 06 — Source verification: what the committed sources actually do

| | |
|---|---|
| Status | Active, v1.0 (2026-09-20). Implements `docs/03-roadmap.md` Phase 4 ("per source — endpoint verified, auth, rate limits observed, terms-of-use notes, quirks, reconciliation mismatches seen"; review F12, F13). |
| Method | Bounded live reads only (plan P4-D2): one `curl` per endpoint per fact, 10 s connect / 25 s total, no retries, `User-Agent: energy-platform-verify/0.1`. Every read is a row of `docs/evidence/README.md` with time, status, size and SHA-256; raw payloads stay in the local evidence directory outside the repository (01 §10). Nothing below is quoted from memory or from a cached web tool. |
| Fixtures | Committed fixtures are **synthetic copies of the real shape** (P4-D3): element names, attributes, header texts, row layout, DST label patterns and item counts copy the live reads listed here; values are invented so a golden can be checked by reading the blob. Live payloads are not committed. |
| Predecessor | `docs/01-data-scope.md` §3 (contracts), §5 (freshness), §10 (admission register). This document records what Phase 4 observed; it changes no contract. Where an observation contradicts 01, the row says so and 01 stays frozen (an ADR would change it). |

## 0. Summary

| Target | Endpoint verified | Auth | Rate limit seen | Terms | Result |
|---|---|---|---|---|---|
| T1 `ote_intraday_market` | `POST https://www.ote-cr.cz/pw-data/services/PublicDataService`, `GetImPricePeriodE`, HTTP 200 for 2024-06-30, 2025-10-26, 2026-03-29, 2026-09-19, 2026-09-20 | none | none (five requests in four seconds, all 200) | OTE Terms of Use: no copying without written consent (§1.4) | shape as 01 §3; 96 / 92 / 100 / 24 items; rolling fill by **item absence** |
| T2 `ote_intraday_market_xlsx` | discovery page + `pubweb/attachments/27/…/IM_15MIN_DD_MM_YYYY_EN.xlsx`, HTTP 200 for 2025-10-26, 2026-03-29, 2026-09-19, 2026-09-20 | none | none | as T1 | header texts contain **newlines**; `ETag` and `Last-Modified` present; rolling fill by **blank cells** |
| T3 `ceps_load` | `POST https://www.ceps.cz/_layouts/CepsData.asmx`, `Load`, HTTP 200 for 2025-10-26, 2026-03-29, 2026-09-19 (QH), plus HR and DY for 2026-09-19 | none | none | `robots.txt` disallows all crawling; the documented web service is used; interface description v3.2 obtained (§4.5) | **F13 resolved: `@date` labels the interval start** (§4.4) |
| E1 `ote_dam` | same endpoint as T1, `GetDamPricePeriodE`, HTTP 200 for 2026-09-20 (PT60M) and 2026-09-21 (PT15M) | none | none | as T1 | request needs `PeriodResolution`; response adds `PeriodInterval`, `HourlyPrice`, `VolumeTotal`; `EmergencyState` absent when not declared; D+1 results already served at 14:24 CEST on D |

No 01 §4 candidate was read. No latency figure is quoted (§6).

## 1. OTE — common facts (T1, T2, E1)

1. **WSDL** (`…/PublicDataService?wsdl`, 56 971 bytes, evidence row 1): `GetImPricePeriodE` takes `StartDate`, `EndDate` (`xs:date`), optional `StartPeriod`/`EndPeriod`; the response `Item` is `Date`, `PeriodResolution`, `PeriodIndex`, optional `Emerg`, optional `Price`, optional `Volume` — exactly 01 §3 T1. `GetDamPricePeriodE` adds a **required** `PeriodResolution` to the request and its `Item` is `Date`, `PeriodResolution`, `PeriodIndex`, `PeriodInterval`, optional `Price`, `HourlyPrice`, `VolumeTotal`, `EmergencyState`. SOAPAction values as in 01 §3.
2. **Auth, headers**: none required; `Content-Type: text/xml; charset=UTF-8` in responses; no `ETag`/`Last-Modified` on SOAP responses (conditional requests do not apply to T1/E1), both present on the XLSX (T2, §2.3).
3. **Rate limits**: none observed on ten requests within a minute; nothing in the WSDL or the terms states a limit. The platform's politeness (ADR-033 §2) stays the only limit.
4. **Terms of Use** (`/en/documentation/term-of-use`, read 2026-09-20, evidence row 3): "The Operator has exclusive access to all data published on the Website. Users have no right to reproduce, copy or duplicate the content of the website in any way without the prior written consent of the Operator unless the Operator agrees otherwise with the Users." → the 01 §10 fixture policy (synthetic until written confirmation) is the right one; **V-1/V-3 open item unchanged**: written confirmation of reuse and attribution wording is still needed before any live capture is redistributed. `robots.txt` allows all agents (evidence row 5).
5. **Decimals**: a dot, always; `Price` with 2 decimals, `Volume` with 3 on every item of every day read (T1 2026-09-19: 96 of 96).
6. **Negative and zero prices are real**: minimum average price −4.21 EUR/MWh on 2026-03-29 and −0.17 on 2026-09-20 (T2 files; the T1 items carry the same values). No zero-volume period and no item without `Price` was seen on the four days; the "no trade → absent `Price`" case of 01 §9 is therefore fixture-only, taken from the WSDL's `minOccurs="0"`.

## 2. T1 — `GetImPricePeriodE`

| Fact | Observation | Evidence row |
|---|---|---|
| Ordinary day | 2026-09-19: 96 `Item`s, `PeriodIndex` 1…96, `PeriodResolution` PT15M | 8 |
| Spring DST day | 2026-03-29: **92** items, indices 1…92 | 17 |
| Autumn DST day | 2025-10-26: **100** items, indices 1…100 | 18 |
| Native hourly day | 2024-06-30: **24** items, `PeriodResolution` **PT60M**, indices 1…24 — the period-based operation serves pre-July-2024 days at their native resolution (01 §3 "[UNVERIFIED]" → verified for one day) | 19 |
| Rolling partial day | 2026-09-20 read at 12:24:33Z (14:24 CEST): **58** items, indices 1…58 (period 58 = 14:15–14:30 local, the period in delivery). Missing periods are **absent items**, not items without `Price` | 9 |
| `Emerg` | not present on any of the five days; optional element, mapped as `ignore_fields` (ADR-034) because the registry has no metric for it | 8, 9, 17–19 |
| Fill timing (single observation) | the last published period at 14:24 was the one whose delivery started at 14:15 → publication at or after gate closure, before delivery end; consistent with 01 §5 "around gate closure" | 9 |

**Correction window.** Nothing was observed about corrections (one read per day). The manifest declares `cadence.correction {cron: "7 * * * *", days: 3}` per 01 §5; the runtime verb is Phase 5 (ADR-033).

## 3. T2 — daily XLSX

### 3.1 Discovery and file

The results page (evidence row 7) contains `href="/pubweb/attachments/27/2026/month09/day20/IM_15MIN_20_09_2026_EN.xlsx"` twice, which the manifest's `link_regex` `IM_15MIN_\d{2}_\d{2}_\d{4}_EN\.xlsx` matches; the fallback `url_template` produced the same URL. The fallback also served 2026-09-19, 2026-03-29 and 2025-10-26 (rows 13, 20, 21).

### 3.2 Layout (all four files)

Sheet `IM Results`; row 3 title `Intra-Day Market Results - DD.MM.YYYY`; **row 6 header**; data from row 7; footer `The results contain traded standard quarterly and hourly contracts.` in column A after the last period. The header texts carry **line breaks**:

```text
Period | Time interval | Traded volume\n(MWh) | Traded volume - purchase\n(MWh) | Traded volume - sold\n(MWh)
| Average price\n(EUR/MWh) | Minimal price\n(EUR/MWh) | Maximal price\n(EUR/MWh) | Last price (EUR/MWh)
```

The generic XLSX parser normalises whitespace before matching header text (`parse.generic._norm`), so the manifest keeps the single-line names of 01 §3. `Period` is stored as a **float** (`1.0`); the decoder turns it into `Decimal("1.0")` and the mapping accepts an integral decimal as an index. All numeric cells are numbers, not text; the decimal-comma string case of 01 §9 is fixture-only.

### 3.3 Rolling fill, conditional requests

2026-09-20 read at 12:24:42Z: 58 periods filled, periods 59…96 present with **blank cells** (`None`), so a partial day is 96 rows with NULLs, unlike T1's absent items. `Last-Modified: Sun, 20 Sep 2026 12:16:37 GMT` and `ETag: "6aafcea5-6484"` were served → the fetch layer's `If-None-Match` applies to T2 and a stale poll costs no download.

### 3.4 DST label patterns (copied into the fixtures)

| Day | Rows | Labels around the change |
|---|---|---|
| 2026-03-29 (spring) | 92 | `01:30-01:45`, `01:45-03:00` (bridging), `03:00-03:15` … |
| 2025-10-26 (autumn) | 100 | `02:00-02:15`, `02:15-02:30`, `02:30-02:45`, `02:45-02:00` (bridging), `02:00-02:15` … (the repeated hour) |

The label column is display only (`ignore_fields`); the parser keys on `Period` (01 §3, §7).

### 3.5 Reconciliation with T1 (01 §3 rule 2)

For every period present in both transports on 2026-09-19 (96), 2026-09-20 (58), 2026-03-29 (92) and 2025-10-26 (100): `Average price` equals T1 `Price` within 0.01 EUR/MWh and `Traded volume` equals T1 `Volume` within 0.001 MWh — **0 mismatches in 346 periods**. The `reconciliation_mismatch` event (Phase 2) therefore has no live example yet; it is exercised by the platform tests.

## 4. T3 — ČEPS `Load`

### 4.1 Endpoint, auth, headers

`POST https://www.ceps.cz/_layouts/CepsData.asmx`, `SOAPAction: "https://www.ceps.cz/CepsData/Load"`, HTTP 200, `Content-Type: text/xml; charset=utf-8`; no auth. The WSDL (row 2) types `LoadResult` as `mixed` with `<s:any/>`: the payload schema is not in the WSDL; the live shape is the contract. No rate limit observed (five requests in two minutes).

### 4.2 Live shape (differs from the Phase 2 synthetic shape in the `information` block)

```text
<LoadResponse xmlns="https://www.ceps.cz/CepsData/"><LoadResult>
  <root xmlns="https://www.ceps.cz/CepsData/StructuredData/1.0">
    <information><name>Load</name><date_from>2026-09-19T00:00:00+02:00</date_from>
      <date_to>2026-09-19T23:59:59+02:00</date_to><version>RT</version><function>AVG</function>
      <aggregation>QH</aggregation></information>
    <series><serie id="value1" name="Load including pumping [MW]"/><serie id="value2" name="Load [MW]"/></series>
    <data><item date="2026-09-19T00:00:00+02:00" value1="5951.667" value2="5951.667"/> …
```

`information` carries `name`, `date_from`, `date_to` (with offsets), `version`, `function`, `aggregation` — not the request echo of the Phase 2 example (`dateFrom`, `agregation`). The generic parser does not read that block (it lacks `@date`), so the mapping is unaffected; the committed fixtures copy the live block. Decimals vary: `5720`, `5797.2`, `5951.667` (0–3 places). **`value1` equals `value2` on every QH and HR item of 2026-09-19** while the DY item has `value1=6642.343`, `value2=6419.655`; whether the QH real-time series carries pumping at all is a question for ČEPS, recorded here, not resolved.

### 4.3 DST days

| Day | Items | Around the change |
|---|---|---|
| 2026-03-29 | 92 | `01:45:00+01:00` → `03:00:00+02:00`; `date_from` `+01:00`, `date_to` `+02:00` |
| 2025-10-26 | 100 | `02:45:00+02:00` → `02:00:00+01:00` (the repeated hour carries the other offset) |

Offset-aware parsing (01 §7) is exactly what the labels need; no wall-clock label is ambiguous once the offset is read.

### 4.4 F13 — which edge does `@date` name? **Start.**

Two independent checks on 2026-09-19 (rows 14–16):

1. **HR versus QH.** For each hour h, the HR item labelled `h:00` equals the mean of the four QH items labelled `h:00`, `h:15`, `h:30`, `h:45` with a maximum deviation of 3.16 MW (≈ 0.05 % of ~6000 MW; the residual is the unequal minute counts inside quarter-hours, the interface description says the basic unit is the average minute power). Under end labelling the HR item labelled `h:00` would have to equal the mean of the QH items `h-1:15 … h:00`; the maximum deviation is then 871.7 MW. Start labelling is the only consistent reading.
2. **DY versus QH.** The single DY item of the day is 6642.343; the mean of the 96 QH items labelled `00:00 … 23:45` of that day is 6639.339 (within the same minute-weighting residual). Under end labelling the day would consist of the items labelled `00:15 … 23:45` plus `00:00` of the next day, which the day request does not even return.
3. **Interface description v3.2** (row 24, the DOCX inside the documentation ZIP): "Data with a basic time unit are represented as average minute power output. The aggregation function 'Average' represents average output [MW]; in the 'Hour' aggregation, average output is equal to energy [MWh]." and "The interface operates using local time (CET/CEST) … Example: 2025-10-15T22:00:00 represents 22:00 local time." It does **not** state which edge a label names; the two numeric checks do.

Consequence: the T3 manifest keeps `interval_label: start`, now with this section as its reference instead of `[UNVERIFIED]`; the T3 goldens are authoritative. 01 §3's "[UNVERIFIED]" for other `function` values and non-RT versions stays (not read; the MVP uses AVG/RT only).

### 4.5 Terms and robots

`robots.txt` (row 4): `User-agent: * / Disallow: /`. The web-services page and the interface description document present the service for "structured data delivery" with a test client and a test endpoint (`wwwtest.ceps.cz`); neither states a rate limit nor redistribution terms. The 01 §10 open items for ČEPS (terms of the service, confirmation that the robots rule does not cover the service, rate expectations) **remain open**; the committed fixtures stay synthetic.

## 5. E1 — `GetDamPricePeriodE`

| Fact | Observation | Row |
|---|---|---|
| Request | `PeriodResolution` is mandatory (WSDL); PT15M and PT60M both served | 1, 10, 11 |
| PT15M day | 2026-09-21 requested on 2026-09-20 at 12:24:33Z: **96** items, `PeriodInterval` `00:00-00:15` …, `Price` per quarter-hour, `HourlyPrice` constant across the hour's four quarters (24 distinct values), `VolumeTotal` with 3 decimals, **no `EmergencyState` element** | 10 |
| PT60M day | 2026-09-20: **24** items, `PeriodInterval` `00-01` …, `Price` = `HourlyPrice` | 11 |
| Publication | D+1 results were complete at 14:24 CEST on D → 01 §5 "once after the day-ahead auction" holds for this day; the manifest polls hourly from 12:00 on D-1 with `{next_delivery_day}` (ADR-033 §4) | 10 |
| Not seen | negative DAM prices (minimum 13.56 on 2026-09-21); `EmergencyState = 1` | 10 |

`PeriodInterval` is display only → `ignore_fields`. `EmergencyState` maps to the registered `emergency_state` metric (unit `1`); absent → NULL ("no result").

### 5.1 The adapter-addition demo through the MCP server (plan P4-D5)

`targets/ote_dam/` was built by a JSON-RPC client talking to `energyctl mcp-serve --root . --outbox …` (no `--allow-network`); the client and the transcript (28 requests) are in the local evidence directory (`e1_mcp_transcript.json`). In order:

| Step | Tool | Result |
|---|---|---|
| 1 | `initialize`, `tools/list` | exactly the ADR-007 eight tools |
| 2 | `scaffold_target(ote_dam, soap-xml, ote.dam, www.ote-cr.cz)` | six files, `admission_required: false` |
| 3 | `validate_target` on the scaffold | admission `OK`, surface lists every `REPLACE_ME` (05 C-13) |
| 4 | `write_target_file(fetch.py, "import httpx")` | **refused**, rolled back: file outside the target surface (05 C-48, C-02) |
| 5 | `write_target_file(../ote_intraday_market/manifest.yaml)` | **refused**: escapes `targets/ote_dam/` (05 C-48) |
| 6 | `write_target_file(parser.py)` with `float(...)` | **refused**, rolled back, no file left behind (05 C-49, C-05) |
| 7 | `record_fixture(live: true)` | **refused**: network not enabled for this server (05 C-50) |
| 8 | `write_target_file(manifest.yaml)`, `validate_target` | `OK`; remaining surface problems are the scaffold golden's placeholders |
| 9 | `record_fixture(payload_path=…)` × 7 | Bronze objects from the synthetic payloads staged under the (git-ignored) `.energy_platform/inbox/` |
| 10 | `write_target_file` × 7 goldens, README | last write reports `remaining_problems: []` |
| 11 | `validate_target`, `run_target_tests` | `OK`; surface OK, seven goldens OK (384 / 96 / 368 / 400 / 384 / 0 / 0 rows), pytest exit 0 |
| 12 | `open_pr` | bundle written to the outbox for `target/ote_dam`; the server never pushed |

Outside the server: `scripts/apply_pr_bundle.py` turned the bundle into the branch `target/ote_dam` (one commit, byte-identical to the working copy), `make check` and `make pr-surface BASE=main` are green.

**Harness defect found and fixed on the way (platform commit, not part of the target):** the first `scaffold_target` for `ote.dam` produced a manifest the model refused (`emergency_state.unit` rendered as the YAML integer `1`); the scaffolder now quotes every unit and a regression test pins it.

## 6. Polling-observation campaign (defined, not run — P4-D12)

01 §5 requires one week of polls per target before any latency figure is quoted. Procedure, using only shipped verbs:

```text
every 15 min (T1, T2, T3) / every hour from 12:00 (E1):
  energyctl capture -m targets/<id>/manifest.yaml --bronze-dir <local bronze> --live
afterwards:
  for each capture-log entry with content_changed = true: record (fetched_at, highest PeriodIndex
  or last @date present) → first-seen time per period → latency = first_seen − delivery_start
  (T1/T2/T3) or first_seen − auction time (E1)
```

`content_changed` is computed by Bronze from the payload hash, so a stale poll (T2 `304`, or an identical body) is a successful poll and not a data point. Run it on a laptop or the Phase 5 `local` profile; the ledger is the report. **No figure is quoted here.** The single observations above (T1/T2 in step at 14:24, E1 complete by 14:24 on D-1) are anecdotes, not measurements.

## 7. One live pass through the platform's own fetch path

After the four targets were on their branches, `make live-smoke` (`tests/live/test_smoke.py`, plan
P4-D10) was run **once** by hand on `phase-4/all-targets` at about 12:55Z: one `record_live` per
target for the previous delivery day through `energy_platform.fetch` (ADR-026 layer 2: host and
registry check, resolution and peer check, bounded retries), then decode and generic parse. All four
passed in about one second — the committed manifests fetch, decode and parse against the live
sources, including T2's discovery step and E1's `{next_delivery_day}` request. Values were not
looked at, and nothing from this run was kept (temporary Bronze).

## 8. What was not verified

- Redistribution rights for OTE and ČEPS (01 §10, V-1/V-3): unchanged, human action.
- ČEPS `function` values other than AVG, `version` values other than RT, and history depth.
- OTE history depth beyond the four days read (2024-06-30 works; 01's P2Y is still an assumption).
- Corrections after a delivery day (no second read of any day).
- Any other 01 §4 candidate (deliberately not read). OTE imbalance settlement was read for its
  Route B admission on 2026-09-23 (§9).

## 9. Held-out admission: OTE imbalance settlement (2026-09-23, ADR-022 §3)

Bounded reads for the Route B admission of `ote.imbalance_settlement` (plan P6-D1), made with
`curl` against the same public service as T1; payloads stay in local evidence
(`~/.config/energy-platform/evidence/2026-09-23/`), nothing is committed (01 §10).

| Read | Request | Result | SHA-256 (payload) |
|---|---|---|---|
| WSDL | `GET …/PublicDataService?wsdl` | 57 125 B; `GetImbalanceSettlementPeriodE(Version, StartDate, EndDate, StartPeriod?, EndPeriod?)` | — |
| Daily settlement | `Version 0`, 2026-09-21 | HTTP 200, 60 245 B, 0.07 s, 96 items `PT15M` | `a6a5ecdb62b7d549…` |
| Monthly settlement | `Version 1`, 2026-08-01 | HTTP 200, 60 690 B, 96 items `PT15M` | `9bf676d837312754…` |

Item fields (every item, both reads): `Version`, `Date`, `PeriodResolution`, `PeriodIndex`,
`SystemImbalance`, `Sum`, `PositiveImbalance`, `NegativeImbalance`, `RoundedImbalance`,
`ReCost`, `ImbalanceCost`, `SettlImbalancePrice`, `SettlCounterImbalancePrice`, `PriceWARE`,
`PriceRE`, `PriceWAIM`, `PriceCurve`; the WSDL also allows an optional `Emerg`. Decimal
separator: a dot everywhere. Observed ranges: `SystemImbalance` −76.25 … 66.37 (negative in
42/96 and 86/96 periods), `SettlImbalancePrice` −1 061.42 … 13 481.57 with 41/96 and 9/96
periods at exactly 0.000 (a published zero, not an absence). Values in the thousands are
consistent with Kč/MWh, as 01 §4 records; the service does not state the currency in the
response.

Admission check (not committed, nothing under `targets/`): a scratch manifest for
`ote.imbalance_settlement` validates **OK** and maps the 2026-09-21 payload through the
generic SOAP parser to 288 observations (96 periods × 3 metrics), no quality event, the first
period at 2026-09-20T22:00Z (local midnight), `source_version` = `0`.

Not verified: the meaning of the imbalance sign (`SystemImbalance` published as is), when
versions 1 and 2 appear for a day, history depth, and the fields not admitted.
