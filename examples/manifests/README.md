# Example manifests (Phase 1)

Six manifests that exercise every modality of `schemas/manifest.v1.json`. **Nothing here is
fetched**; the files exist so that the schema, the registries and the two-stage validation
(`docs/04-contracts.md` §3.7) are demonstrated offline. They live outside `targets/` on purpose:
no target exists before the Phase 3 harness (`docs/03-roadmap.md`, "harness before code").

| File | Modality | Source | `validate_manifest` |
|---|---|---|---|
| `ote_idm_soap.yaml` | `soap-xml` | T1 — OTE continuous intraday, `GetImPricePeriodE` (01 §3) | `OK` |
| `ote_idm_xlsx.yaml` | `dated-file` | T2 — OTE daily XLSX with HTML discovery step (01 §3) | `OK` |
| `ceps_load_soap.yaml` | `soap-xml` | T3 — ČEPS `Load`, QH/AVG/RT (01 §3) | `OK` |
| `ote_idm_html_table.yaml` | `html-table` | shape-only: the OTE results page renders the same table with a decimal comma (S02) | `OK` |
| `token_api_rest_json.yaml` | `rest-json` | shape-only: token-keyed JSON API via `secretRef` | `ADMISSION_REQUIRED` |
| `entsoe_rest_xml.yaml` | `rest-xml` | shape-only: ENTSO-E Transparency (class B, token, rate-limited XML; 01 §4) | `ADMISSION_REQUIRED` |

The last two are the ADR-022 Route B demonstration: the manifest is structurally valid, and
validation lists exactly the dataset, metrics and host a maintainer would have to admit. Nothing
is invented to make them pass.

Values marked `[UNVERIFIED]` in comments follow `docs/01-data-scope.md`; the ČEPS `interval_label`
was verified in Phase 4 (review F13, `docs/06-source-verification.md` §4.4).
