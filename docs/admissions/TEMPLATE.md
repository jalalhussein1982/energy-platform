# Admission request — `{{target_id}}` ({{date}})

| | |
|---|---|
| Route | **B — source admission** (ADR-022 §1). This file is the whole PR; the registry change it asks for is a maintainer's platform PR under CODEOWNERS. |
| `energyctl validate {{target_id}}` | `{{status}}` |
| Proposed `dataset_id` | `{{dataset_id}}` |
| Unregistered datasets | {{missing_datasets}} |
| Unregistered metrics | {{missing_metrics}} |
| Unregistered hosts | {{missing_hosts}} |
| Hosts needing `allow_insecure` | {{missing_insecure_hosts}} |

## Validation errors (registered but inconsistent, if any)

{{errors}}

## Source

| | |
|---|---|
| Endpoint / modality | {{modality}} on {{allowed_hosts}} |
| License / terms | {{license}} — {{terms_url}} |
| Redistribution of raw captures confirmed? | REPLACE_ME (01 §10) |
| Publication cadence and latency observed | REPLACE_ME (01 §5; one week of polling before quoting a figure) |

## Proposed contract (01 §6.3 / §9 — the maintainer decides; nothing here is a registry edit)

| Item | Proposal |
|---|---|
| Identity key | REPLACE_ME, e.g. `(bidding_zone, delivery_start_utc, resolution)` |
| Fixed / constrained dimensions | REPLACE_ME |
| Resolutions | REPLACE_ME |
| Revision marker (`source_version`) | REPLACE_ME or none |

| Metric (as declared in the manifest) | Unit | Sign | Separator |
|---|---|---|---|
{{declared_metrics}}

For each metric the maintainer needs: unit **as published**, sign rule (`negative_allowed`,
`non_negative`, `non_negative_expected`), what NULL means, currency if any, and which transport
is the system of record when several deliver it.

## Sample shape

REPLACE_ME — a bounded excerpt of one response (element/column names, one row), no credentials,
no bulk data. A synthetic fixture with the real shape may accompany the later Route A PR.

## What the requester will do once admitted

Open a Route A PR touching only `targets/{{target_id}}/` (manifest, fixtures, goldens, tests).
