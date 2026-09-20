# 04 — Contracts: canonical schema (ADR-011) and manifest schema (ADR-013)

| | |
|---|---|
| Status | Active, v1.0 (2026-09-20). Implements `docs/03-roadmap.md` Phase 1. The code in `energy_platform/contracts/` is the normative form; this document explains it and cites where every field comes from. |
| Source of truth for fields | `docs/01-data-scope.md` §3 (targets), §6 (envelope, time, identity keys), §7 (time contract), §8 (revisions), §9 (value semantics). No field is invented here and none is dropped (02 ADR-011 note). |
| Parameters fixed by | ADR-017 (manifest format), ADR-018 (storage form), ADR-019 (parsers, decimals), ADR-022 (registries, admission), ADR-023 (derivation identity), ADR-024 (`history.max_age`), ADR-026 (host registry, `allow_insecure`), ADR-027 (decoded parser input). |
| Formalisations made here | Listed in `docs/plans/phase-1.md` "Decisions taken by this plan" (P1-D1 … P1-D7). They fix *representation*; they add no field and no policy. |

## 1. One contract, two sides

A target describes **what a source looks like** (§3, the manifest). The platform guarantees **what
the destination looks like** (§2, the canonical observation). Everything in between — fetch,
decode, mapping, persistence — is platform code that reads the manifest and writes observations.
A target can therefore be wrong about *syntax* (a column name, a selector) but never about
*semantics* (a unit, a timezone, a sign): those come from the registries (§2.4, §2.5, §4) and the
platform rejects a manifest that disagrees with them.

```text
manifest.yaml ──validate──▶ Manifest ──(Phase 2: fetch → decode → parser → mapping)──▶ EnergyObservation ──▶ Silver
       ▲                       │ admission                                                     ▲ registry
       └── schemas/manifest.v1.json      └── DATASETS, HOSTS ◀────────────────────────────────┘
```

## 2. ADR-011 — the canonical observation (`energy_platform/contracts/observation.py`)

### 2.1 Envelope (01 §6.1, ADR-023)

| Field | Type | Source | Rule |
|---|---|---|---|
| `source_id` | str | 01 §6.1 | must equal the registered dataset's `source_id` |
| `dataset_id` | str | 01 §6.1 | must exist in `DATASETS` (§2.4) |
| `source_transport` | `soap \| xlsx \| html \| rest` | 01 §6.1 | which transport delivered this row |
| `contract_version` | semver | 01 §6.1, ADR-023 | version of the registered dataset contract |
| `derivation_id` | 16 hex | ADR-023 §1 | identity of the implementation that produced the row (§2.6) |
| `raw_ref` | str | 01 §6.1 | immutable Bronze key of the raw document |
| `payload_sha256` | 64 hex | 01 §6.1 | hash of the raw payload |
| `fetched_at` | aware datetime, stored UTC | 01 §6.1 | always present |
| `source_published_at` | aware datetime or NULL | 01 §6.1 | **never** filled from `fetched_at` |
| `source_version` | str or NULL | 01 §6.1 | the source's own revision marker (OTE settlement 0/1/2, ČEPS RT/DF/IDF) |
| `processed_at` | aware datetime | 01 §6.1 | when parsing happened |

Every datetime must be timezone-aware on input and is normalised to UTC (ADR-014 bans naive
datetimes; the model rejects them).

### 2.2 Time fields (01 §6.2, ADR-018)

| Field | Type | Rule |
|---|---|---|
| `delivery_interval` | `DeliveryInterval(start, end)` — UTC, `[start, end)` | the `tstzrange` form of 01's `delivery_start_utc` / `delivery_end_utc`; both exposed as properties |
| `resolution` | ISO 8601 duration (`PT15M`, `PT60M`, …) | must be one the dataset declares; for `kind=interval` the interval length must equal it |
| `local_date` | date | source civil date (Europe/Prague) used for period indices |
| `period_index` | int ≥ 1 or NULL | source index within `local_date`, when the source uses one |
| `kind` | `interval \| point` | AVG samples are intervals; a future 1-minute frequency series would be `point` |

`energy_platform/contracts/intervals.py` implements the 01 §7 rule **period index → local
interval → UTC**: `local_day_intervals(date, resolution)` tiles the civil day from local midnight
to the next local midnight, so the count is 96, 92 (spring) or 100 (autumn) by construction;
`interval_for_index` maps a 1-based index; `interval_from_timestamp(ts, resolution, label)` maps an
offset-aware timestamp that names the interval `start` or `end`. Property tests cover 2020–2030.

### 2.3 Rows are metric-long; observation identity (P1-D1, P1-D2)

One `EnergyObservation` is **one metric value for one observation identity**:

| Field | Type | Rule |
|---|---|---|
| `dimensions` | mapping str → str | exactly the identity-key dimensions that are neither time fields nor `version` (§2.4); fixed values must match the registry |
| `metric` | str | must be registered for the dataset |
| `value` | `Decimal` or NULL | NULL means what the metric's registry row says (§2.5), never zero |
| `unit` | str | must equal the registry unit — no conversion in the contract |
| `sign_convention` | `as_published \| inverted` | the manifest's declared sign rule, recorded on the row |

**Observation identity** (01 §8) = `(dataset_id, dimensions, delivery_start_utc, resolution, metric,
source_version)`. `source_version = NULL` is a value in the identity (ADR-023 §5). Two bindings
make 01 §6.3 keys and 01 §6.1 envelope agree: `delivery_start_utc` and `resolution` come from the
time fields; the `version` dimension of `ceps.load` **is** the envelope `source_version` (P1-D2).

Why metric-long: 01 §3 assigns ownership per metric (T1 owns `price_vwap`/`volume_total`; T2 owns
the other five and is not backed by T1), and 01 §9 keeps a per-metric registry. A wide row could
not say "T2 absent, T1 present" without inventing nullability semantics.

### 2.4 Dataset registry (`registry.py`, ADR-022; seeded from 01 §6.3)

| `dataset_id` | source | identity key (01 §6.3 order) | fixed / constrained dimensions | resolutions | `contract_version` |
|---|---|---|---|---|---|
| `ote.idm_continuous` (T1, T2) | `ote` | `(bidding_zone, delivery_start_utc, resolution)` | `bidding_zone = CZ` | `PT15M`, `PT60M` | 1.0.0 |
| `ote.dam` (E1) | `ote` | `(bidding_zone, delivery_start_utc, resolution)` | `bidding_zone = CZ` | `PT15M`, `PT60M` | 1.0.0 |
| `ceps.load` (T3) | `ceps` | `(area, delivery_start_utc, resolution, aggregation_function, version)` | `area = CZ`; `aggregation_function ∈ {AVG}` (only AVG is live-verified, 01 §3); `version` ← `source_version` | `PT15M` | 1.0.0 |

Candidates in 01 §6.3 (`ote.imbalance_settlement`, `ote.ida`, `ceps.crossborder_flows`,
`ceps.generation`, forecasts) are **not** registered. Registering one is Route B (§5).

### 2.5 Metric registry (`registry.py`; seeded from 01 §9)

| dataset | metric | unit | currency | sign rule | NULL means | owner transport |
|---|---|---|---|---|---|---|
| `ote.idm_continuous` | `price_vwap` | EUR/MWh | EUR | negative allowed | no trade in period, or not yet published | `soap` (T1) |
| | `volume_total` | MWh | — | ≥ 0 enforced | not yet published | `soap` (T1) |
| | `volume_buy`, `volume_sell` | MWh | — | ≥ 0 enforced | not yet published | `xlsx` (T2) |
| | `price_min`, `price_max`, `price_last` | EUR/MWh | EUR | negative allowed | no trade in period, or not yet published | `xlsx` (T2) |
| `ote.dam` | `price`, `price_hourly` | EUR/MWh | EUR | negative allowed | no result | `soap` |
| | `volume_total` | MWh | — | ≥ 0 enforced | no result | `soap` |
| | `emergency_state` | `1` (dimensionless flag) | — | ≥ 0 | no result | `soap` |
| `ceps.load` | `load_incl_pumping`, `load` | MW | — | ≥ 0 expected, not enforced (quality event only) | missing sample | `soap` |

Sign rules: `negative_allowed`, `non_negative` (enforced at mapping time, Phase 2),
`non_negative_expected` (raises a quality event, never rejects — 01 §9 "not enforced").
Native currency is preserved; any conversion is a derived value with FX source and date (01 §9).

### 2.6 Versions, upsert key, current view (01 §8, ADR-018, ADR-023)

| Version | Meaning | Changes when |
|---|---|---|
| `source_version` | the source's revision marker, or NULL | the source says so |
| `contract_version` | semver of the registered dataset contract | the *meaning* of a field or the identity key changes (Route B) |
| `derivation_id` | first 16 hex of SHA-256 over canonical JSON of `{platform_version, contract_version, mapping_block, parser_ref}` | any code or mapping that can change an output value changes |

`mapping_block` is `Manifest.mapping_block()` (the `mapping` section, JSON mode, `None` fields
dropped); `parser_ref` is `generic:<parser>@<platform_version>` or `custom:<sha256 of parser.py>`.

- **Version identity = upsert key** (`version_identity()`) = observation identity + `payload_sha256`
  + `derivation_id`. Exact retry inserts nothing; same payload with a new derivation appends; a
  provider correction (new payload) appends regardless of derivation. Nothing is overwritten.
- **Current view** (Phase 2 SQL), per observation identity: highest ordering basis
  (`source_published_at` if present, else `fetched_at` of the *capture*, never the replay time);
  then highest `contract_version`, then latest `derivations.registered_at`; the view records
  `ordering_basis`. A late replay of an old document never becomes current.
- **Unchanged retry** (same `payload_sha256`): one new fetch-log entry, no new version.

### 2.7 DST and interval rules (01 §7)

Store UTC; keep `local_date` and `period_index`. Intervals are start-inclusive, end-exclusive.
Expected quarter-hours per local day are computed from the calendar (96 / 92 / 100). The autumn
XLSX repeats `02:xx` labels and the spring XLSX carries a bridging `01:45-03:00` label; both are
display only — the parser keys on `Period`, and the manifest declares which edge a timestamp names
(`interval_label`). Native resolution is preserved; resampling is a separate derived dataset.

### 2.8 Value rules (01 §9; enforced by the Phase 2 mapping engine)

Numbers are parsed with `decimal.Decimal` under an explicit separator (`decimals.parse_decimal`);
thousands separators, exponents, `NaN`/`inf` and mixed separators raise and quarantine the
document. Blank cells and absent elements become NULL, never zero. Unknown columns, changed header
text, unit-label changes and currency mismatches quarantine the whole document with a reason. MW
versus MWh is checked against the registry, not inferred.

## 3. ADR-013 — the manifest (`energy_platform/contracts/manifest.py`)

### 3.1 File conventions (ADR-017)

`targets/<id>/manifest.yaml`: one YAML document; no anchors, aliases, merge keys, tags or
multiple documents (`load_manifest` scans the token stream and raises `ManifestSyntaxError`).
`schema_version: 1`. `schemas/manifest.v1.json` is exported from the model by `make schema`; a
test fails when it is stale. A breaking change bumps the major and ships a converter. Secrets are
never values: only `secretRef {name, key}` (§3.4), and any credential-looking string in the
`fetch` block is rejected. If `targets/<id>/parser.py` exists it exposes exactly one class
implementing `Parser` (§3.8).

### 3.2 Top-level fields

| Field | Required | Type / rule |
|---|---|---|
| `schema_version` | yes | literal `1` |
| `target_id` | yes | `^[a-z][a-z0-9_]{2,63}$` (matches the directory name) |
| `description` | no | free text |
| `license` | yes | non-empty: the terms under which the data is reused (01 §10 row) |
| `terms_url` | yes | `https` URL |
| `allowed_hosts` | yes | ≥ 1 lowercase hostnames, no wildcards, no IPs; every URL in `fetch` must use one of them; each must be in the host registry (§4, admission) |
| `allow_insecure` | no (false) | `http` is allowed only when this is true **and** the host registry entry allows it (ADR-026 §2) |
| `modality` | yes | `soap-xml \| dated-file \| html-table \| rest-json \| rest-xml` |
| `cadence` | yes | `{cron: "<5 fields>", timezone: "<IANA zone>"}`; the CronJob schedule (ADR-003 rev.) |
| `history` | yes | `{max_age: "<ISO 8601 duration>" \| "none"}` — how far back the source still serves data; the gap detector consults it before backfilling (ADR-024 §5) |
| `fetch` | yes | exactly one modality-named block (§3.3) |
| `contract` | yes | §3.5 |
| `mapping` | yes | §3.6 |

Unknown fields are errors (`extra="forbid"`), at every level.

### 3.3 `fetch` blocks (ADR-005: declarative, per modality)

The block key must match `modality` (P1-D3). URLs must be literal about scheme and host;
placeholders (`{delivery_day:%Y-%m-%d}`, `{scheduled_for}`) may appear only in path, query and
body. A URL must not carry a port (ports come from the host registry).

| Modality | Key | Fields |
|---|---|---|
| `soap-xml` | `soap_xml` | `url`, `soap_action`, `soap_version` (`1.1` default, `1.2`), `body_template` (SOAP body with `{name}` placeholders), `params` (placeholder → expression) |
| `dated-file` | `dated_file` | `file_format` (`xlsx \| csv`, must equal `contract.decode`), `url_template` (direct URL), optional `discovery {url, link_regex}` — fetch a page, extract the link, then download (T2) |
| `html-table` | `html_table` | `url`, `table_selector` (CSS) |
| `rest-json` | `rest_json` | `url_template`, `query`, `headers`, optional `auth` (§3.4), optional `rate_limit {requests, per}` |
| `rest-xml` | `rest_xml` | same fields as `rest_json` |

Placeholder expressions are rendered by the Phase 2 fetch layer from the run context
(`delivery_day`, `scheduled_for`); Phase 1 only checks that they contain no credential.

### 3.4 `secretRef`

```yaml
auth:
  secretRef: {name: entsoe-token, key: securityToken}   # Kubernetes Secret name and key (env in `local`)
  location: query | header
  param: securityToken                                  # query parameter or header name
```

The platform resolves the reference at fetch time. Fixtures, logs and the manifest itself never
see the value.

### 3.5 `contract` block (ADR-022, ADR-027)

| Field | Rule |
|---|---|
| `dataset_id` | must be registered (§2.4) — otherwise `ADMISSION_REQUIRED` |
| `source_transport` | `soap \| xlsx \| html \| rest`; must fit the modality (`soap-xml`→`soap`, `dated-file`→`xlsx` or `rest` for a csv file, `html-table`→`html`, `rest-*`→`rest`) |
| `decode` | `xlsx \| xml \| soap \| json \| html-table \| csv`; must fit the modality; the platform decodes raw bytes into a `DecodedDocument` (§3.8) before any parser runs |
| `metrics` | ≥ 1, unique; each must be registered for the dataset; must equal the keys of `mapping.metrics` |

### 3.6 `mapping` block (ADR-005 normalise; executed by the platform in Phase 2)

```yaml
mapping:
  dimensions: {bidding_zone: CZ}          # identity dims other than time fields and `version`
  time:
    kind: period_index | timestamp
    timezone: Europe/Prague
    resolution: {source: PeriodResolution} | {constant: PT15M}
    date:  {source: Date} | {context: delivery_day}     # period_index only
    index: {source: PeriodIndex}                        # period_index only
    timestamp: {source: "@date"}                        # timestamp only (offset-aware)
    interval_label: start | end                         # which edge the timestamp names
  source_version: {constant: RT} | {source: Version} | null
  source_published_at: {source: ...} | null            # never derived from fetch time
  metrics:
    price_vwap: {source: Price, unit: EUR/MWh, sign: as_published, decimal_separator: dot}
```

A `FieldRef` is exactly one of `source` (a field of the `SourceRecord`), `constant`, or
`context` (`delivery_day`, `scheduled_for` from the run). Admission checks that `dimensions`
keys equal the dataset's non-time, non-version identity dimensions, that fixed values match
(`bidding_zone = CZ`), that constrained values are allowed (`aggregation_function = AVG`), that a
dataset with `version` in its key maps `source_version`, that a constant `resolution` is declared
for the dataset, and that every `unit` equals the registry unit. `decimal_separator` is `dot` or
`comma`, never auto-detected (P1-D6). `sign` is `as_published` or `inverted`.

### 3.7 Validation: two stages, one result shape (ADR-022 §2)

1. **Structural** — `Manifest.model_validate` / `load_manifest`. Failures raise
   `pydantic.ValidationError` (or `ManifestSyntaxError` for the YAML subset). Covers everything in
   §3.1–§3.6 that needs no registry: mandatory fields, block ↔ modality ↔ transport ↔ decode,
   host ∈ `allowed_hosts`, scheme, no port, no credential-looking string, `contract.metrics` =
   `mapping.metrics`.
2. **Admission** — `validate_manifest(manifest) -> ValidationResult`:

```json
{"status": "OK | INVALID | ADMISSION_REQUIRED",
 "errors": ["metric volume_total: unit 'MW' must be the registry unit 'MWh'"],
 "missing": {"datasets": ["entsoe.day_ahead_prices"],
             "metrics": [["entsoe.day_ahead_prices", "price"]],
             "hosts": ["web-api.tp.entsoe.eu"],
             "insecure_hosts": []}}
```

`ADMISSION_REQUIRED` lists exactly what a Route B request must add; `INVALID` means registered
but inconsistent with the registry. Both are reported together; precedence
`ADMISSION_REQUIRED > INVALID > OK`. Phase 3's `energyctl validate <id>` prints this object.
Inventing a unit, editing a registry from a target PR, or marking a metric "unknown" to pass are
the failure modes the Phase 3 gates reject.

### 3.8 Parser protocol and decoded documents (ADR-027 §2, `parser.py`)

```text
Parser.parse(doc: DecodedDocument) -> Iterable[SourceRecord]
DecodedDocument = TabularDocument(kind: csv|html-table, header, rows)
               | SheetsDocument(sheets: name → rows)                    # xlsx
               | XmlDocument(kind: xml|soap, root: XmlElement)          # read-only element view
               | JsonDocument(data)
SourceRecord(fields: Mapping[str, Cell], locator: str)   # Cell = str | Decimal | int | bool | None
```

The platform decodes bytes per `contract.decode` first; a custom parser never sees bytes and
needs no third-party import (`parser.py` may import only `energy_platform.contracts` and the
pure-data stdlib modules listed in `scripts/check_target_surface.py`). A parser emits records in
the **source's** vocabulary; units, timezones, intervals and signs are applied by the platform
from `mapping`. `XmlElement.find_all` / `first` match on local names (namespaces stripped).

## 4. Host registry (`hosts.py`, ADR-026 §2)

| host | ports | `allow_insecure` | for |
|---|---|---|---|
| `www.ote-cr.cz` | 443 | no | T1, T2, E1 |
| `www.ceps.cz` | 443 | no | T3 |

Exact, case-insensitive match; no wildcards, no IP literals. The Phase 2 fetch layer checks the
manifest's `allowed_hosts` **and** this registry on every request and every redirect hop.
`web-api.tp.entsoe.eu` is deliberately absent (ENTSO-E is unadmitted, 01 §10).

## 5. Change control

| Change | Route | Touches |
|---|---|---|
| New target for a registered dataset, registered hosts, registered metrics | A (adapter addition) | `targets/<id>/` only; CI + one human approval of goldens |
| New `dataset_id`, metric, unit, sign rule, NULL meaning, dimension value, host, or `allow_insecure` | B (source admission) | `registry.py` / `hosts.py` (CODEOWNERS), a 01 §10 row, where needed an ADR; `contract_version` bumps when a field's meaning or the identity key changes |
| Field added to the envelope, time block or manifest schema | ADR + schema major bump + converter | platform PR |

Open formalisation questions are recorded as Route B items, never resolved by adding a field in
a target.

## 6. Where the tests are

| Rule | Test |
|---|---|
| 92 / 96 / 100 intervals, index and label mapping, offset-aware ČEPS timestamps | `tests/contracts/test_intervals.py` (Hypothesis over 2020–2030) |
| decimal comma/dot, rejection of ambiguous text, sign inversion | `tests/contracts/test_decimals.py` |
| registry contents match 01 §6.3 / §9; candidates absent | `tests/contracts/test_registry.py`, `test_hosts.py` |
| observation validation, identity axes, `derivation_id` | `tests/contracts/test_observation.py` |
| parser protocol, stdlib-only import surface | `tests/contracts/test_parser.py` |
| every structural rule and every admission gap, `ADMISSION_REQUIRED` shape | `tests/contracts/test_manifest.py`, `test_manifest_negative.py` |
| exported schema current and complete | `tests/contracts/test_schema_export.py` |
| six example manifests (`examples/manifests/`) | `tests/contracts/test_examples.py` |
