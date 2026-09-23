# Plan — Phase 6: Threat model, triage pipeline, documentation (2026-09-23)

> **For agentic workers:** execute task by task. One task = one commit, `make check` green before
> each commit (03 §0). Everything here is a platform commit on `main` (the maintainer bypasses
> branch protection by the logged admin route, option (a) of 2026-09-23).

| | |
|---|---|
| Goal | `docs/threat-model.md` complete; the drift-triage pipeline runs end to end with the LLM stubbed and the prompt-injection tests pass; a junior can add a target from one page; the held-out source is admitted and **not** built; architecture diagram. |
| Spec | `docs/03-roadmap.md` Phase 6; ADR-006 … ADR-009 (`02`); ADR-022 (Route B, held-out admission); ADR-026, ADR-027; `02` §4.2 D-10 ("pipeline built, LLM step stubbed, documented"); `05-constraint-matrix.md`. |
| Do not | Build the held-out target (`targets/ote_imbalance_settlement/` must not exist before Phase 7). Put any LLM call in the capture/process path. Add a dependency. Let triage write anything but a proposal file. Weaken a gate. |

## Author decisions (2026-09-23)

- Held-out candidate: **OTE imbalance settlement** (`GetImbalanceSettlementPeriodE`).
- Branch protection: option (a) — review and 12 required checks, admins may bypass (logged).
- No week of waiting: the one-week polling campaign (Phase 4) and V-11 (Phase 5) are **closed as
  not run**, documented, no figure quoted.

## Decisions taken by this plan

| # | Decision | Why |
|---|---|---|
| P6-D1 | **Held-out admission = `ote.imbalance_settlement`**, `source_id` `ote`, identity `(bidding_zone, delivery_start_utc, resolution, version)` with `bidding_zone = CZ` and `version` ← `source_version` (the response's `Version`: 0 daily, 1 monthly, 2 final monthly — `04` §2 already names "OTE settlement 0/1/2"), resolutions `PT15M` (from 2024-07-01) and `PT60M`, partition `day`. Metrics: `system_imbalance` (MWh), `imbalance_price` and `counter_imbalance_price` (CZK/MWh, currency CZK), all `negative_allowed` (the 2026-09-23 live reads show negative values in each), NULL = "not yet published". Host `www.ote-cr.cz` is already registered. The Route B platform PR: registry entry + tests, a row in `01` §10 (ADR-022 §1 assigns that row to Route B; this is the one sanctioned `01` edit), `docs/admissions/ote_imbalance_settlement.md` (the admission record, decided), `docs/06` §9 (bounded live reads). **No adapter.** | ADR-022 §3; contract confirmed live (01 §4); the generic SOAP parser covers it, so Phase 7 run 1 does not depend on the unbuilt custom-`parser.py` loader. |
| P6-D2 | **Numbering:** the junior's guide is `docs/08-adding-a-target.md` (07 is the operations runbook since Phase 5); the Phase 7 report becomes `docs/09-acceptance-report.md`; the roadmap wording follows. | Avoid a second `07`. |
| P6-D3 | **Triage pipeline** in `energy_platform/triage/` (library; CLI verb `energyctl triage`): `detect` (production mapping over the drifted Bronze fixture → `DriftReport`: quarantine reason, `unknown_field` names, metrics whose source never appears) → `extract` (bounded sample: field inventory from the production parser, ≤ 3 example records, each value ≤ 64 chars with control characters removed, whole sample ≤ 4 000 chars, serialised as JSON data) → `propose` (`LLMBackend.complete(system, user)`; the system prompt is a constant, the untrusted sample travels only inside the user message as JSON) → `constrain` (strict JSON schema; allowed operations only: `rename_source` for a metric or time field, `set_decimal_separator`, `add_ignore_field`; every new source name must appear in the extracted inventory and match `^[A-Za-z_][A-Za-z0-9_.@-]{0,63}$`; the patched manifest must validate and differ from the original only under `mapping.metrics.*.source`, `mapping.metrics.*.decimal_separator`, `mapping.time.*.source`, `mapping.ignore_fields`) → `verify` (the patched manifest maps the drifted payload without quarantine and with no new `unknown_field`) → **proposal file** `outbox/triage-<id>-<stamp>.json` (unified diff of `targets/<id>/manifest.yaml` only, the report, the LLM rationale truncated and labelled untrusted). Never a push, never a registry, fetch, unit, sign, host, licence or cadence change: those are not expressible as operations and are refused again by the diff check. | ADR-008 mandatory flow; ADR-007 least privilege; D-10. |
| P6-D4 | **LLM backends:** `LLMBackend` Protocol (ADR-009); `HeuristicStubBackend` (default, deterministic, no network: proposes a rename to the closest unmapped field by `difflib`); `UnavailableBackend` (always raises) for the ADR-009 hard requirement. The OpenAI-compatible HTTP client is **not built** (D-10: stubbed); `docs/threat-model.md` §1 says where it would go (inside `energy_platform/fetch/`, its host in the host registry). | D-10; no egress outside `fetch/` (ADR-027). |
| P6-D5 | **Tests** (`tests/triage/`, offline): `test_extractor.py::test_sample_is_bounded_and_data_only`, `::test_hostile_text_is_truncated_and_stripped`; `test_pipeline.py::test_renamed_field_yields_manifest_only_proposal`, `::test_no_drift_no_proposal`, `::test_llm_unavailable_returns_no_proposal`; `test_injection.py::test_hostile_xml_cannot_change_unit_sign_host_or_url`, `::test_hostile_html_cannot_widen_the_patch`, `::test_invented_source_field_rejected`, `::test_proposal_touches_only_the_target_manifest`, `::test_system_prompt_is_constant`. The malicious backend in `test_injection.py` *obeys* the injected text (the worst case of a compromised model): the gate must hold anyway. New `05` rows C-58 … C-61 cite them. | "Stop when the prompt-injection tests pass" (03 Phase 6). |
| P6-D6 | **Threat model:** each ADR-008 catalogue item gets Mechanism / Gate (with the `05` row and the test) / Residual risk; plus the triage agent's own items. | 03 Phase 6. |

## Tasks

### Task 6.1 — Held-out admission (Route B): `ote.imbalance_settlement`
- [x] Registry entry; `tests/contracts/test_registry.py` (registered set, the candidate list without it, `CZK/MWh` ↔ `CZK`, the contract test).
- [x] `01` §10 row; `docs/admissions/ote_imbalance_settlement.md`; `docs/06` §9 (the two bounded reads, hashes, field inventory).
- [x] Commit `feat(registry): admit ote.imbalance_settlement through Route B (ADR-022 §3 held-out source)`.

### Task 6.2 — Triage pipeline with the LLM stubbed
- [x] `energy_platform/triage/{__init__,llm,extract,pipeline}.py`, `energyctl triage`, tests P6-D5, `05` rows C-58 … C-61.
- [x] Commit `feat(triage): drift-triage pipeline with a stubbed LLM, bounded extraction and a manifest-only proposal (ADR-008, ADR-009, D-10)`.

### Task 6.3 — Threat model
- [ ] `docs/threat-model.md` complete. Commit `docs(threat-model): ...`.

### Task 6.4 — The junior's page and the architecture diagram
- [ ] `docs/08-adding-a-target.md` (both routes; every command run once while writing it, on a scratch target outside `targets/`); `docs/architecture.md` (Mermaid). Commit `docs: ...`.

### Task 6.5 — Close-out
- [ ] Roadmap: Phase 6 ticks, P6-D2 renumbering, the polling campaign and V-11 closed as not run; progress entry with the Phase 7 prompts. Commit `docs(phase-6): ...`.

## Acceptance

`make check` green; `tests/triage/` passes (prompt-injection cases included); `energyctl triage` on a
drifted T1 fixture writes a manifest-only proposal; `energyctl validate` on a scratch manifest
for `ote.imbalance_settlement` returns OK (admitted) while `targets/ote_imbalance_settlement/`
does not exist; `docs/threat-model.md` has no "—" left.
