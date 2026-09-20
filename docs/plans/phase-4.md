# Plan — Phase 4: Committed-target verification through the harness (2026-09-20)

> **For agentic workers:** execute task by task. One task = one commit, `make check` green before
> each commit (03 §0). Steps use `- [ ]` checkboxes. Target work happens on `target/<id>`
> branches produced by the harness; platform work is committed on `main`.

| | |
|---|---|
| Goal | The harness's first real workload: T1, T2, T3 built at Level 1 authority through `energyctl new-target` → `record-fixture` → goldens → `pr-bundle`, then E1 added last through the constrained-agent route (MCP server) as the adapter-addition demo. Stop when all four pass contract tests offline. |
| Spec | `docs/03-roadmap.md` Phase 4; `docs/01-data-scope.md` §3, §5, §7, §9, §10; `docs/04-contracts.md`; `docs/05-constraint-matrix.md`; ADR-020, ADR-022, ADR-026, ADR-027; the starter prompt in `docs/progress.md`. |
| Architecture | No new platform module. Two small additive contract changes decided by ADR before any target exists (ADR-033 D-5 cadence, ADR-034 `mapping.ignore_fields`) plus one harness fix (an empty document is a golden outcome). Everything else is data under `targets/<id>/`, evidence under `docs/evidence/`, findings in `docs/06-source-verification.md`. |
| Tech | No new dependency. Live reads are bounded `curl` / `energyctl … --live` calls with 10 s connect and 25 s total timeouts, no retries, one request per endpoint per fact. |
| Do not | Edit `energy_platform/` from a target branch. Commit a live capture (01 §10). Add a 01 §4 candidate. Edit docs/00, 01, 02. Weaken a gate. Merge to `main` (Level 3). Quote a latency figure without the one-week campaign. |

## Global constraints (copied from the spec)

- A target is exactly the ADR-027 surface; fetch and normalise are declared in the manifest,
  never coded (05 C-01…C-07). A target PR touches only `targets/<id>/` (05 C-39…C-41).
- Fixtures are Bronze objects written by `energyctl record-fixture`; committed fixtures are
  **synthetic copies of the real shape** until OTE/ČEPS confirm redistribution (01 §10, ADR-020);
  live samples stay in local evidence with their digests.
- Goldens list values a human checked against the fixture document, `checked_by` filled
  (ADR-020; 05 C-16, C-17). Required cases (01 §7, §9; 03 Phase 4): ordinary day, 23-hour day,
  25-hour day, native hourly sample, partially filled day, negative and zero prices, absent
  `Price`, empty `<Result/>`, decimal-comma string, extra column, changed unit header, complete
  day with a legitimate no-trade NULL, rolling partial day, SOAP fault over HTTP 200.
- Every datetime aware; delivery intervals `[start, end)`; DST days 92/100 by the calendar.
- Registry entries are platform PRs (ADR-022); an unadmitted source gets an admission request.
- Unit tests run with sockets disabled; the live smoke is marked `live` and never runs in PR CI.

## Decisions taken by this plan (formalisations, not new policy)

| # | Decision | Why |
|---|---|---|
| P4-D1 | Target ids are the roadmap's: `ote_intraday_market` (T1), `ote_intraday_market_xlsx` (T2), `ceps_load` (T3), `ote_dam` (E1). `examples/manifests/` keeps its Phase 1 ids; examples are schema demonstrations, targets are the committed contracts. | 03 Phase 4 names them; the Phase 1 examples were written before the harness and are referenced by tests. |
| P4-D2 | Live reads: one bounded request per endpoint per fact (`curl`, or `energyctl record-fixture --live` into a scratch target), timeouts 10 s connect / 25 s total, no retries; the raw payload and its SHA-256 go to `~/.config/energy-platform/evidence/2026-09-20/` (outside the repository); `docs/evidence/README.md` lists request shape, observation time, digest and the bounded facts extracted (review F12). | 01 §10 fixture policy; the F12 ledger was never supplied, so the index is regenerated from this session's reads. |
| P4-D3 | Committed fixtures are synthetic: payloads generated from the live-verified shape with values chosen so a reader can check each golden row by opening the blob (`grep`/`openpyxl`), then wrapped by `energyctl record-fixture --from-file`. Each target README lists every fixture with what it demonstrates and how its values were chosen. The generator scripts live in the evidence directory, not in the repository, because a target may hold no script (ADR-027). | ADR-020 "produced only by `record-fixture`"; 01 §10. |
| P4-D4 | A target PR is `energyctl pr-bundle` → `scripts/apply_pr_bundle.py` → branch `target/<id>` cut from `main`; `make check` and `make pr-surface BASE=main` are run on the branch. Merging is Level 3 and stays with the maintainer; an integration branch `phase-4/all-targets` (never `main`) proves the four coexist under `make check`. | ADR-006 authority; P3-D2 (the harness prepares, never pushes or merges). |
| P4-D5 | T1–T3 go through the CLI (developer mode, the README steps); E1 goes through the MCP server only (`scaffold_target`, `write_target_file`, `validate_target`, `record_fixture`, `run_target_tests`, `open_pr`), driven by a JSON-RPC client script kept outside the repository. | 03 Phase 4: E1 is "added last, by the contributor workflow, as the adapter-addition demo"; ADR-007 makes the MCP route the constrained-agent contributor workflow. |
| P4-D6 | An empty document is a golden outcome: `expect: {row_count: 0}` with no rows and no quarantine is valid; a golden with neither rows, nor quarantine, nor `row_count` stays refused (05 C-16). | 01 §9 requires the empty `<Result/>` fixture; the Phase 3 model could not express its expected outcome (zero rows, no quarantine). |
| P4-D7 | ADR-034 `mapping.ignore_fields`: source fields the document carries and the mapping deliberately does not read (T2 `Time interval`, T1 `Emerg`, E1 `PeriodInterval`); a name that is also mapped is a manifest error; ignored fields raise no `unknown_field`; any other unmapped field still does. Schema v1 stays (additive optional field). | 04 §5 open question, carried since Phase 2; three of four committed targets would otherwise warn on every run, which makes the warning worthless. |
| P4-D8 | ADR-033 (D-5): cadence per 01 §5 in `cadence.cron`; retries, jitter, backoff caps and conditional requests are the fetch layer's as built; the correction window is an optional `cadence.correction: {cron, days}` block whose runtime form (re-capture of a past delivery day's run, `force`, new attempt) is a Phase 5 task with the CronJob template. Phase 4 adds the manifest field and the ADR, not the verb. | 03 Phase 4 asks for the ADR; nothing in a golden depends on the verb; the run identity question (04 §5 delivery-day offset) is answered by re-capture, not by a new identity axis. |
| P4-D9 | F13: the ČEPS labelling verdict is whatever the ČEPS interface description or an independent reference supports; if neither can be read, `interval_label: start` stays `[UNVERIFIED]` in the manifest comment, the T3 goldens carry a `note:` saying the times are not authoritative, and `docs/06` says exactly what was tried. | 03 Phase 4 F13 wording; never quietly upgrade an unverified fact. |
| P4-D10 | Nightly live smoke = `tests/live/test_smoke.py` (platform test, marked `live`), parametrised over committed targets: one bounded `record_live` into a temporary Bronze, assert decode + generic parse succeed and the record count is a non-negative integer — shape only, never values. `make live-smoke` runs it; `.github/workflows/nightly-live-smoke.yml` (`schedule` + `workflow_dispatch`) calls only Make. `tests/harness/test_ci_wrappers.py` is extended to every workflow file. | ADR-020 nightly smoke; ADR-015 thin workflows; a target may not import `energy_platform.fetch`, so the smoke is platform code. |
| P4-D11 | `epex_intraday` negative demo = a scaffold in a scratch targets root whose `energyctl validate` says `ADMISSION_REQUIRED` and whose `energyctl admission-request` writes `docs/admissions/epex_intraday.md` listing the gaps (host, dataset, metrics) with the terms note; no directory under `targets/` (an incomplete target fails collection by design). The "scheduler refuses `license: restricted`" rule belongs to the Phase 5 CronJob renderer and is recorded there. | ADR-022 Route B; 05 C-54; ADR-020 collection rule. |
| P4-D12 | The one-week polling campaign is **defined** (procedure in `docs/06` §6 using `energyctl capture --live` on a cron loop into a local Bronze, latency read from the capture log's `content_changed` transitions) and **not run**; no latency figure is quoted anywhere. | 01 §5; wall clock. |

## Ordered tasks

### Task 4.1 — Plan and ADRs

**Files:** this file, `docs/adr/ADR-033-polling-cadence-and-correction-window.md`,
`docs/adr/ADR-034-mapping-ignore-fields.md`.

- [x] ADR-033 ACCEPTED: 01 §5 values, fetch-layer politeness as built (cite `RetryPolicy`,
      `Conditional`, `RateLimiter`), `cadence.correction` shape, re-capture semantics, Phase 5 hand-off.
- [x] ADR-034 ACCEPTED: `mapping.ignore_fields`, validation rule, effect on `unknown_field`,
      `derivation_id` note (part of `mapping_block()`), schema minor.
- [x] Commit `docs(phase-4): plan, ADR-033 (D-5 cadence and correction window), ADR-034 (mapping.ignore_fields)`.

### Task 4.2 — Contract changes decided above (platform)

**Files:** `energy_platform/contracts/manifest.py` (`Cadence.correction`, `MappingBlock.ignore_fields`),
`energy_platform/mapping/engine.py`, `energy_platform/contracts/golden.py`, `energy_platform/harness/goldens.py`,
`schemas/manifest.v1.json` (`make schema`), `docs/04-contracts.md` §3.2, §3.6, §5 (question closed),
`tests/contracts/test_manifest.py`, `tests/contracts/test_manifest_negative.py`, `tests/mapping/…`,
`tests/contracts/test_golden.py`, `tests/harness/test_goldens.py`.

- [x] `cadence.correction: {cron, days ≥ 1}` optional; cron validated like `cadence.cron`.
- [x] `mapping.ignore_fields: [str, …]` optional; an entry equal to a mapped `source` (time, version,
      metric) is a `ValidationError`; the engine subtracts them before `unknown_field`.
- [x] `Expect`: `row_count: 0` alone is valid; runner reports `row_count` mismatch as before; the
      negative "empty golden" test still fails on a golden with nothing expected.
- [x] `make schema`; schema staleness test green; 04 updated; `make check` green.
- [x] Commit `feat(contracts): cadence.correction and mapping.ignore_fields (ADR-033, ADR-034); an empty document is a golden outcome`.

### Task 4.3 — Live verification and evidence index

**Files:** `docs/06-source-verification.md`, `docs/evidence/README.md`; local evidence directory
(outside the repo).

- [x] Bounded reads, each with time, status, digest, size: OTE WSDL; T1 `GetImPricePeriodE` for
      one recent day; E1 `GetDamPricePeriodE` for one day (both `PeriodResolution` values if the
      WSDL requires the element); T2 results page (link discovery) and the daily XLSX for one recent
      day; ČEPS WSDL; T3 `Load` QH/AVG/RT for one day; OTE terms page; `ceps.cz/robots.txt`;
      the ČEPS web-services page and any linked interface description.
- [x] F13: read the interface description (or the WSDL annotations); record the verdict per P4-D9.
- [x] `docs/06`: per source — endpoint verified, auth, rate limits observed, terms notes (V-1, V-3),
      quirks (decimal comma, DST rows, progressive fill), reconciliation mismatches seen, F13 outcome,
      the polling campaign procedure (P4-D12), the fixture inventory pointer.
- [x] `docs/evidence/README.md` (F12): one row per read; raw captures not committed.
- [x] Commit `docs(sources): live verification of T1, T2, T3, E1 endpoints; evidence index (F12); F13 outcome`.

### Task 4.4 — T1 `ote_intraday_market` (branch `target/ote_intraday_market`)

- [x] `energyctl new-target ote_intraday_market --modality soap-xml --dataset ote.idm_continuous --host www.ote-cr.cz`;
      manifest filled from 01 §3 T1 and the live WSDL (`ignore_fields: [Emerg]`, `cadence.correction`).
- [x] Fixtures (synthetic, `--from-file`): `ordinary_day` (96), `spring_dst_day` (92, 2026-03-29),
      `autumn_dst_day` (100, 2025-10-26), `hourly_native` (PT60M, 24, a 2024-06 day), `partial_day`
      (rolling, first 40 periods), `no_trade_null` (complete day, one period without `Price`),
      `negative_and_zero_price`, `empty_result`, `decimal_comma`, `soap_fault`, `emerg_flag`.
- [x] Goldens: values read from the blobs; `row_count`; `quality_events`; quarantine reasons.
- [x] README: fixture table, what the platform does with each, what is not in this target.
- [x] `energyctl validate`, `run-target-tests`, `make check`, `energyctl pr-bundle`,
      `python -m scripts.apply_pr_bundle`, `make pr-surface BASE=main` on the branch.

### Task 4.5 — T2 `ote_intraday_market_xlsx` (branch `target/ote_intraday_market_xlsx`)

- [x] Scaffold with `--modality dated-file`; manifest per 01 §3 T2 (discovery + fallback template,
      `ignore_fields: ["Time interval"]`).
- [x] Fixtures: `ordinary_day` (96), `spring_dst_day` (92, bridging label), `autumn_dst_day` (100,
      repeated labels), `partial_day` (10 of 96 filled), `no_trade_null` (zero volumes, NULL prices),
      `negative_and_zero_price`, `decimal_comma_string` (a text cell), `extra_column`,
      `changed_unit_header` (CZK/MWh → quarantine).
- [x] Goldens, README, gates, bundle, branch, `pr-surface` as in 4.4.

### Task 4.6 — T3 `ceps_load` (branch `target/ceps_load`)

- [x] Scaffold with `--dataset ceps.load`; manifest per 01 §3 T3; `interval_label` per the F13 verdict.
- [x] Fixtures: `ordinary_day` (96), `spring_dst_day` (92, offset change inside the day),
      `autumn_dst_day` (100, repeated wall-clock hour with two offsets), `partial_day`,
      `missing_value` (an item without `value2`), `negative_load` (`negative_value` warning),
      `empty_data`, `decimal_comma`, `soap_fault`.
- [x] Goldens (with `note:` when F13 stays unverified), README, gates, bundle, branch, `pr-surface`.
- [x] `docs/06` F13 section finalised on `main` if the verdict changed after 4.3 — docs commit.

### Task 4.7 — E1 `ote_dam` through the MCP server (branch `target/ote_dam`)

- [x] Start `energyctl mcp-serve --root . --outbox <scratch>` and drive it with a JSON-RPC client
      (outside the repo): `scaffold_target` → `write_target_file` (manifest, README, goldens, test,
      fixture entry + blob) → `validate_target` → `run_target_tests` → `open_pr`. Every refusal met on
      the way is recorded in `docs/06` §E1 as the demo's evidence.
- [x] Fixtures: `ordinary_day` (PT15M, 96), `hourly_day` (PT60M, 24), `spring_dst_day`,
      `autumn_dst_day`, `no_result`, `negative_price`, `soap_fault`.
- [x] Apply the bundle; `make check`; `make pr-surface BASE=main`.

### Task 4.8 — `epex_intraday` negative demo (Route B)

- [x] Scaffold in a scratch targets root; `energyctl validate` → `ADMISSION_REQUIRED`;
      `energyctl admission-request epex_intraday --out docs/admissions/` → `docs/admissions/epex_intraday.md`
      with the terms note ("restricted; not to be scraped") and the gaps exactly as reported.
- [x] Commit `docs(admissions): epex_intraday admission request as the Route B negative demo (ADR-022, 05 C-54)`.

### Task 4.9 — Nightly live smoke

**Files:** `tests/live/__init__.py`, `tests/live/test_smoke.py`, `Makefile` (`live-smoke`),
`.github/workflows/nightly-live-smoke.yml`, `tests/harness/test_ci_wrappers.py`, `docs/05-constraint-matrix.md` §2 (inventory row).

- [x] Test discovers `targets/*/` at collection; marked `live`; one `record_live` per target into a
      temporary directory; asserts decode and parse only.
- [x] `make live-smoke` = `pytest -m live tests/live`; `make test` still deselects `live`.
- [x] Workflow: `schedule: "17 3 * * *"` + `workflow_dispatch`, `permissions: contents: read`,
      steps `make ci-bootstrap`, `make live-smoke`; action pinned (05 C-42).
- [x] `test_ci_workflow_only_calls_make` covers every `.github/workflows/*.yml`.
- [x] Commit `feat(ci): nightly live smoke over committed targets, shape only (ADR-020; P4-D10)`.

### Task 4.10 — Integration proof and close

- [x] Branch `phase-4/all-targets` from `main`, merge the four `target/*` branches, `make check`
      green, `pytest tests/harness/test_goldens.py -q` lists every golden; delete nothing.
- [x] `docs/03-roadmap.md` Phase 4 checkboxes (honest: the polling campaign and the EPEX scheduler
      rule are recorded, not ticked); `docs/04-contracts.md` §6 rows; `docs/05` §2 `live-smoke` row;
      `docs/progress.md` entry with the next prompt (03 Phase 5 starter, verbatim).
- [x] Commit `docs(phase-4): roadmap, contracts test table, progress`.

## Acceptance for the phase

On each `target/<id>` branch: `make check` green, `make pr-surface BASE=main` green, every golden
runs through `tests/harness/test_goldens.py`. On `phase-4/all-targets`: `make check` green with all
four targets. On `main`: `make check` green, `targets/` still only `__init__.py`,
`docs/06-source-verification.md` and `docs/evidence/README.md` present, ADR-033 and ADR-034 accepted,
`docs/admissions/epex_intraday.md` present.
