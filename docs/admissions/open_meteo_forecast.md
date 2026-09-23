# Admission request — `open_meteo_forecast` (2026-09-23)

| | |
|---|---|
| Route | **B — source admission** (ADR-022 §1). This file is the whole PR; the registry change it asks for is a maintainer's platform PR under CODEOWNERS. |
| Status | **REQUESTED — not admitted; no target implemented** |
| `energyctl validate open_meteo_forecast` | `ADMISSION_REQUIRED` |
| Proposed `dataset_id` | `open_meteo.forecast` |
| Unregistered datasets | `open_meteo.forecast` |
| Unregistered metrics | `open_meteo.forecast.temperature_2m` |
| Unregistered hosts | `api.open-meteo.com` |
| Hosts needing `allow_insecure` | none |

## Validation errors (registered but inconsistent, if any)

- none

Validated on 2026-09-23 against base `b233ac5110af244ec391653e5e37ab5e68fbd2a4`.
The CLI scaffold and candidate manifest were kept outside the repository under
`/tmp/ep-run2-admission/targets/`; no candidate adapter is part of this request.

```bash
uv run python -m energy_platform.cli new-target open_meteo_forecast \
  --modality rest-json --dataset open_meteo.forecast --host api.open-meteo.com \
  --targets-root /tmp/ep-run2-admission/targets
# Filled the candidate manifest with the proposed metric/unit and endpoint below.
uv run python -m energy_platform.cli validate open_meteo_forecast \
  --targets-root /tmp/ep-run2-admission/targets
# Exit 2; validation.status = ADMISSION_REQUIRED; validation.errors = []
uv run python -m energy_platform.cli admission-request open_meteo_forecast \
  --targets-root /tmp/ep-run2-admission/targets
```

The missing dataset, metric and host are exactly those reported above. Separate surface
diagnostics reported unfinished scaffold goldens and missing fixtures; these are expected for
an admission probe, not a passing Route A target. No fixture recording or target tests ran.

## Source

| | |
|---|---|
| Endpoint / modality | HTTPS GET, `rest-json`: [requested endpoint](https://api.open-meteo.com/v1/forecast?latitude=50.08&longitude=14.42&hourly=temperature_2m) |
| Scope | Hourly forecast temperature at requested coordinates 50.08 N, 14.42 E (Prague); proposed `source_id: open_meteo` |
| License / terms | Data: CC-BY-4.0. The [API terms](https://open-meteo.com/en/terms) state: "You may only use the free API services for non-commercial purposes." Commercial deployment needs a maintainer-approved service arrangement. |
| Redistribution of raw captures confirmed? | The [licence page](https://open-meteo.com/en/licence) permits sharing/adaptation with attribution, a licence link and disclosure of changes; it also requires an Open-Meteo link where data are displayed. Project-specific approval is pending. No real captures are committed. |
| Publication cadence and latency observed | **[UNVERIFIED]** No polling campaign or successful live capture. Proposed initial polling: once per hour, subject to review and observation; this is not a measured publication cadence or freshness SLA. |
| Rate limits | The free-service [terms](https://open-meteo.com/en/terms) require fewer than 10,000 calls/day, 5,000/hour and 600/minute. Retries and all consumers must share the budget. |
| Host requested | `api.open-meteo.com`, port 443 only; no insecure HTTP, wildcard or additional host requested |

Official documentation and terms were read on 2026-09-23. The web reader could not retrieve
the requested endpoint; its live response remains **[UNVERIFIED]**. The platform host registry
was not widened to obtain a sample.

The [API documentation](https://open-meteo.com/en/docs) describes Celsius, GMT timestamps,
seven forecast days and automatic model selection as defaults. `temperature_2m` is an
instantaneous temperature at two metres, not an hourly average. `hourly.time` and
`hourly.temperature_2m` are parallel arrays; `hourly_units` carries units. Returned coordinates
identify the selected grid cell, which can differ from the requested point.

## Proposed contract (01 §6.3 / §9 — the maintainer decides; nothing here is a registry edit)

| Item | Proposal |
|---|---|
| Identity key | Proposed `(location, delivery_start_utc, resolution)` for a latest-captured forecast series; maintainer must approve forecast identity semantics |
| Fixed / constrained dimensions | Proposed `location: "50.08,14.42"` denotes the requested point; do not identify it as national load or use returned grid coordinates as a changing identity. Admit other locations/model selections separately. |
| Resolutions | Proposed native sampling resolution `PT60M`; representing an instant with the platform's interval envelope needs explicit approval |
| Revision marker (`source_version`) | Proposed NULL unless a reliable provider marker is verified; do not invent an issue time from capture time |
| `source_published_at` | Proposed NULL; `generationtime_ms` describes generation duration, not publication time ([API documentation](https://open-meteo.com/en/docs)) |
| Capture ordering | Subject to approval, use ADR-023 capture-time ordering and append-only payload/derivation history; this does not identify or reconstruct model runs |
| History / corrections | **[UNVERIFIED]** for this contract. Proposed no historical backfill initially (`history.max_age: none` in the probe); agree a bounded correction policy before implementation. |

| Metric (as declared in the manifest) | Unit | Sign | Separator |
|---|---|---|---|
| `temperature_2m` | `°C` | as_published | dot |

Proposed registry sign: `negative_allowed`; zero and negative Celsius values are valid.
Currency: none. Proposed owning transport: `rest`. The published unit is `°C`
([API documentation](https://open-meteo.com/en/docs)); this request does not substitute an
energy unit or register a unit. Proposed NULL meaning: unavailable forecast sample, never zero;
the provider's exact reasons for NULL are **[UNVERIFIED]**. Missing arrays or unequal lengths
should quarantine as structural errors, rather than silently dropping samples.

Before admission, a maintainer must decide:

- Whether weather forecasts belong in the platform's approved scope and whether latest-capture
  ordering is adequate. If model-run/issue-time identity is required, obtain that evidence and
  agree the contract first.
- How forecast valid instants fit `delivery_interval`, and how future forecast coverage fits
  the day-based scheduling, completeness and freshness rules. Their suitability is
  **[UNVERIFIED]**, not established by manifest validation.
- How to turn the documented offset-less GMT strings into aware UTC instants through the
  platform time contract. Do not interpret them as Europe/Prague wall time. A later fixture
  suite must check both Prague DST transitions at hourly resolution.
- How to read named parallel arrays with equal-length validation under ADR-027, and verify
  `hourly_units.temperature_2m` before mapping. Any required platform capability belongs in a
  separate platform PR, not target fetch/normalisation code.
- Which metadata to retain in Bronze and deliberately exclude from metric mapping: grid
  coordinates, elevation, generation duration and timezone metadata. Unit/time metadata must
  be validated before being ignored as measurements.

## Sample shape

Synthetic, one-sample illustration based on the documented JSON structure; values are
invented for illustration, not a live observation or a Bronze fixture:

```json
{
  "latitude": 50.1,
  "longitude": 14.4,
  "generationtime_ms": 0.25,
  "utc_offset_seconds": 0,
  "timezone": "GMT",
  "timezone_abbreviation": "GMT",
  "elevation": 200.0,
  "hourly_units": {"time": "iso8601", "temperature_2m": "°C"},
  "hourly": {"time": ["2026-09-23T00:00"], "temperature_2m": [-1.2]}
}
```

## What the requester will do once admitted

After human admission and resolution of the decisions above, open a Route A PR touching only
`targets/open_meteo_forecast/` (manifest, optional parser, README, Bronze fixtures and hand-read
goldens). Cover ordinary, empty, NULL/zero/negative, DST, malformed arrays, unit drift and
forecast revision cases. This request stops at Route B as required by the contributor guide
§10 and ADR-022 §2; it changes no registry, allowlist, target, dependency or deployment.
