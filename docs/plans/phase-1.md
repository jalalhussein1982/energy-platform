# Plan — Phase 1: Contracts (2026-09-20)

> **For agentic workers:** execute task by task with `superpowers:executing-plans` (inline) or
> `superpowers:subagent-driven-development`. Steps use `- [ ]` checkboxes. One task = one commit,
> `make check` green before each commit (03 §0).

| | |
|---|---|
| Goal | The two sides of the one contract: what a source looks like (manifest) and what the destination looks like (canonical observation). Gate: six example manifests validate against `schemas/manifest.v1.json`; DST property tests pass. |
| Spec | `docs/03-roadmap.md` Phase 1; `docs/01-data-scope.md` §3, §6–§9 (frozen source of truth for fields); `docs/02-architecture-decisions.md` ADR-005, ADR-011, ADR-013; `docs/adr/` ADR-017, ADR-018, ADR-019, ADR-020, ADR-022, ADR-023, ADR-024, ADR-026, ADR-027. |
| Architecture | `energy_platform/contracts/` is a pure-data package (Pydantic v2 models, frozen dataclasses, pure functions). No I/O beyond reading a YAML file. Registries are Python constants under CODEOWNERS. Validation is two-staged: **structural** (Pydantic + exported JSON Schema) and **admission** (registries; ADR-022 `ADMISSION_REQUIRED`). |
| Tech | Python 3.12, `pydantic` v2, `pyyaml`, `tzdata`, `hypothesis` (all already approved: ADR-019 / ADR-014); `types-pyyaml` via new ADR-029. |
| Do not | Write fetch, parse (decoders), mapping-execution or persistence code. Fetch from the network. Create anything under `targets/`. Edit docs/00, 01, 02. Weaken a gate. |

## Global constraints (copied from the spec)

- Every datetime is aware; delivery intervals are `tstzrange`-equivalent, start-inclusive, end-exclusive (ADR-018); DST days have 92/100 quarter-hours computed from the calendar, never hard-coded (01 §7).
- Envelope fields exactly as 01 §6.1; time fields exactly as 01 §6.2; identity keys exactly as 01 §6.3; no field invented, none dropped (ADR-011 note in 02).
- Three versions, three meanings: `source_version`, `contract_version`, `derivation_id` = first 16 hex of SHA-256 over canonical JSON of `{platform_version, contract_version, mapping_block, parser_ref}` (ADR-023 §1). Version identity = (observation identity, `payload_sha256`, `derivation_id`) (ADR-023 §2).
- Manifest: YAML, one document, no anchors/merges/custom tags; `schema_version: 1`; JSON Schema exported from the Pydantic model to `schemas/manifest.v1.json`; secrets only as `secretRef {name, key}`; mandatory `license`, `terms_url`, `allowed_hosts`, `cadence`, `modality`, `fetch`, `mapping` (ADR-017); `contract` block with registered `dataset_id`, `metrics` ⊆ registered set, `decode` (ADR-022, ADR-027); `history.max_age` (ADR-024); `allow_insecure` (ADR-026).
- `allowed_hosts` ⊆ host registry; `http` needs `allow_insecure: true` in the manifest **and** on the registry entry; ports 443 unless the entry allows another (ADR-026 §2).
- `Parser.parse(doc: DecodedDocument) -> Iterable[SourceRecord]`; decode kinds `xlsx | xml | soap | json | html-table | csv` (ADR-027 §2). `parser.py` may import only `energy_platform.contracts` + the stdlib list in `scripts/check_target_surface.py`.
- Decimal comma is parsed explicitly with `decimal.Decimal`; never `float()` on raw strings (ADR-019, CLAUDE.md).
- Dependencies: only names approved by an ADR and listed in `deps-allowlist.txt` (transitive closure included).
- Unit tests run with sockets disabled (`conftest.py`); nothing here is `live`.

## Decisions taken by this plan (formalisations, not new policy)

| # | Decision | Why |
|---|---|---|
| P1-D1 | **Silver rows are metric-long**: one `EnergyObservation` = one metric value for one observation identity. Observation identity = 01 §6.3 identity key ⊕ `metric` ⊕ `source_version`. | 01 §3 rules 2–4 assign *ownership per metric* (T1 owns `price_vwap`/`volume_total`, T2 the other five) and 01 §9 keeps a *per-metric* registry; a wide row cannot express "T2 absent, T1 present" without inventing nullability semantics. `metric` is a 01 §9 name, not an invented field. |
| P1-D2 | Identity dimension `version` (ceps.load) is **bound to the envelope `source_version`**; `delivery_start_utc` and `resolution` are bound to the time fields; every other identity dimension is a constant in `mapping.dimensions` and must equal the registry's fixed value. | 01 §6.1 lists ČEPS RT/DF/IDF as `source_version`; 01 §6.3 lists `version` in the ceps.load key. One value, two names. |
| P1-D3 | The `fetch` block is keyed by modality (`fetch.soap_xml`, `fetch.dated_file`, `fetch.html_table`, `fetch.rest_json`, `fetch.rest_xml`); exactly one key is set and it must match top-level `modality`. | Keeps `modality` a mandatory top-level field (ADR-017) and gives a JSON Schema with one object per modality instead of a discriminator that pure JSON-Schema validators cannot resolve. |
| P1-D4 | Example manifests live in `examples/manifests/` (not `targets/`: harness before code). The three real ones pass admission; the three shape-only ones are structurally valid and return `ADMISSION_REQUIRED` naming their unadmitted dataset/metrics/hosts. | Demonstrates both routes of ADR-022 offline. `targets/` stays empty until Phase 3. |
| P1-D5 | Roadmap wording fix: ENTSO-E Transparency serves **XML** with a token and a rate limit, so it is the `rest-xml` (rate-limited) example; the `rest-json` (keyed) example is a generic token-keyed JSON API shape. | 01 §4 describes ENTSO-E as REST + token; the "rest-json-keyed = ENTSO-E's shape" parenthetical in 03 was wrong on format. Roadmap is not frozen; the line is corrected in task 1.11. |
| P1-D6 | `decimal_separator` is `dot` or `comma`, per metric, never auto-detected. | CLAUDE.md "parse explicitly"; `1,234` is ambiguous. |
| P1-D7 | `types-pyyaml` is a dev dependency under a new one-paragraph **ADR-029** ("typing stubs for an allowlisted runtime package are dev dependencies covered by that package's ADR"). | `mypy --strict` rejects untyped `yaml`; suppressing the import would weaken a gate. |

## File map

| Path | Responsibility |
|---|---|
| `docs/adr/ADR-029-typing-stubs.md` | P1-D7 |
| `pyproject.toml`, `uv.lock`, `deps-allowlist.txt` | runtime deps `pydantic`, `pyyaml`, `tzdata`; dev `types-pyyaml` |
| `docs/04-contracts.md` | ADR-011 + ADR-013 written together; source = 01 §6–§9 |
| `energy_platform/contracts/intervals.py` | ISO-8601 duration subset, `DeliveryInterval`, local-day intervals (DST-safe), index→interval, timestamp+label→interval |
| `energy_platform/contracts/decimals.py` | `parse_decimal(text, separator)`, `apply_sign(value, sign)` |
| `energy_platform/contracts/registry.py` | `MetricSpec`, `DatasetContract`, `DATASETS`, `dataset(dataset_id)` — seeded from 01 §6.3/§9 |
| `energy_platform/contracts/hosts.py` | `HostEntry`, `HOSTS`, `host(name)` — seeded from 01 §3 |
| `energy_platform/contracts/observation.py` | `EnergyObservation`, `observation_identity()`, `version_identity()`, `derivation_id()` |
| `energy_platform/contracts/parser.py` | `DecodedDocument` shapes, `SourceRecord`, `Parser` protocol |
| `energy_platform/contracts/manifest.py` | `Manifest` model tree, `load_manifest(path)`, `validate_manifest(manifest) -> ValidationResult` |
| `energy_platform/contracts/__init__.py` | public re-exports |
| `schemas/manifest.v1.json` | exported JSON Schema (committed; test asserts it is current) |
| `scripts/export_manifest_schema.py` + `make schema` | regenerates the file |
| `examples/manifests/*.yaml` | six example manifests (P1-D4) |
| `tests/contracts/test_*.py` | unit, property and negative tests |

---

### Task 1.1 — ADR-029 and dependencies

**Files:** create `docs/adr/ADR-029-typing-stubs.md`; modify `pyproject.toml`, `deps-allowlist.txt`; regenerate `uv.lock`.

- [ ] **Step 1: ADR-029** (one paragraph, ADR-template layout, status ACCEPTED, date 2026-09-20): "A `types-<pkg>` stub distribution for a package already approved by an ADR is a dev-group dependency covered by that ADR; it is listed in `deps-allowlist.txt` with a comment naming the runtime package. Rationale: `mypy --strict` (ADR-014) must not be weakened by `ignore_missing_imports`. Rejected: per-module mypy overrides (weakens a gate); vendoring a typed wrapper (duplicates upstream)."
- [ ] **Step 2: pyproject.** `dependencies = ["pydantic>=2.9,<3", "pyyaml>=6.0", "tzdata>=2024.1"]`; dev group gains `"types-pyyaml>=6.0"`. Add `"examples"` to `[tool.ruff] src`? No — examples hold YAML only. Add `[tool.hatch.build.targets.wheel] packages` unchanged.
- [ ] **Step 3:** `uv lock` (network allowed here: it is not a unit test). Then `uv run python scripts/check_deps_allowlist.py uv.lock deps-allowlist.txt` — expected FAIL listing `pydantic`, `pydantic-core`, `annotated-types`, `typing-inspection`, `tzdata`, `types-pyyaml` (exact set = whatever the lock adds).
- [ ] **Step 4:** add those names to `deps-allowlist.txt` under a header `# --- runtime, Phase 1 (ADR-019) + stubs (ADR-029), locked 2026-09-20 ---`; remove `pydantic`, `pyyaml`, `tzdata` from the "not yet locked" comment. Rerun the allowlist check → PASS. `make check` → green.
- [ ] **Step 5: Commit** `build(deps): pydantic, pyyaml, tzdata (ADR-019) and types-pyyaml (ADR-029) for the contracts package`.

### Task 1.2 — `docs/04-contracts.md` (ADR-011 + ADR-013)

**Files:** create `docs/04-contracts.md`.

Sections, in order, each citing its 01/ADR source line; no field invented, none dropped:

- [ ] **§1 Scope and reading guide** — two sides of one contract; what is frozen (01) and what this doc fixes (parameters).
- [ ] **§2 ADR-011 canonical observation** — 2.1 envelope (01 §6.1 verbatim list + `derivation_id` per ADR-023); 2.2 time fields (01 §6.2; `delivery_interval` as the tstzrange form of `delivery_start_utc`/`delivery_end_utc`); 2.3 metric-long rows and observation identity (P1-D1, P1-D2); 2.4 dataset registry table (T1/T2 → `ote.idm_continuous`, E1 → `ote.dam`, T3 → `ceps.load`, identity keys, fixed dimensions, `contract_version 1.0.0`); 2.5 metric registry table (unit, currency, sign rule, null meaning; from 01 §9); 2.6 version identity and upsert key (ADR-023 §2), current-view order (ADR-023 §3), NULL `source_version` (§5); 2.7 DST and interval rules (01 §7; 92/100 computed); 2.8 quarantine rules (01 §9 last paragraph) — stated, implemented in Phase 2.
- [ ] **§3 ADR-013 manifest** — 3.1 file conventions (ADR-017); 3.2 top-level fields table (`schema_version`, `target_id`, `description`, `license`, `terms_url`, `allowed_hosts`, `allow_insecure`, `modality`, `cadence`, `history`, `fetch`, `contract`, `mapping`); 3.3 fetch blocks per modality with every field; 3.4 `secretRef`; 3.5 `contract` block; 3.6 `mapping` block (dimensions, time, source_version, source_published_at, metrics with unit/sign/decimal_separator); 3.7 validation: structural vs admission, the `ValidationResult` shape and the `ADMISSION_REQUIRED` payload (ADR-022 §2); 3.8 parser protocol and `DecodedDocument` shapes (ADR-027 §2).
- [ ] **§4 Host registry** (ADR-026 §2) — table of seeded hosts.
- [ ] **§5 Change control** — what is a Route A vs Route B change; `contract_version` bump rules.
- [ ] Commit `docs(contracts): 04-contracts — canonical schema (ADR-011) and manifest schema (ADR-013)`.

### Task 1.3 — `intervals.py` with DST property tests

**Files:** create `energy_platform/contracts/intervals.py`, `tests/contracts/__init__.py`, `tests/contracts/test_intervals.py`.

**Produces:**
```text
def parse_duration(text: str) -> timedelta            # "PT15M" | "PT60M" | "PT1H" | "PT1M" | "P1D"; else ValueError
@dataclass(frozen=True) class DeliveryInterval: start: datetime; end: datetime   # aware, start < end; __post_init__ validates
def local_day_intervals(local_date: date, resolution: str, tz: str = "Europe/Prague") -> tuple[DeliveryInterval, ...]
def interval_for_index(local_date: date, period_index: int, resolution: str, tz: str = "Europe/Prague") -> DeliveryInterval   # 1-based; IndexError outside the day
def interval_from_timestamp(ts: datetime, resolution: str, label: Literal["start", "end"]) -> DeliveryInterval   # ts must be aware
```
Implementation: `midnight = datetime.combine(local_date, time(), tzinfo=ZoneInfo(tz))`; `next_midnight = datetime.combine(local_date + 1 day, ...)`; convert both to UTC, step by `parse_duration(resolution)`; store intervals in UTC. Never add a tzinfo to a wall-clock label inside the day.

- [ ] **Step 1: failing tests**
```text
from datetime import UTC, date, datetime
from hypothesis import given, strategies as st
from energy_platform.contracts.intervals import (DeliveryInterval, interval_for_index, interval_from_timestamp, local_day_intervals, parse_duration)

def test_spring_day_has_92_quarter_hours(): assert len(local_day_intervals(date(2026, 3, 29), "PT15M")) == 92
def test_autumn_day_has_100_quarter_hours(): assert len(local_day_intervals(date(2025, 10, 26), "PT15M")) == 100
def test_ordinary_day_has_96(): assert len(local_day_intervals(date(2026, 9, 18), "PT15M")) == 96
def test_hourly_native_day_has_24(): assert len(local_day_intervals(date(2024, 6, 30), "PT60M")) == 24

@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)))
def test_intervals_tile_the_local_day(d):
    ivs = local_day_intervals(d, "PT15M")
    assert ivs[0].start == datetime.combine(d, datetime.min.time(), tzinfo=ZoneInfo("Europe/Prague")).astimezone(UTC)
    assert all(a.end == b.start for a, b in zip(ivs, ivs[1:]))
    assert all(iv.end - iv.start == timedelta(minutes=15) for iv in ivs)
    assert len(ivs) in {92, 96, 100}
    assert ivs[-1].end == datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=ZoneInfo("Europe/Prague")).astimezone(UTC)

def test_autumn_index_maps_second_0200_hour_distinctly():
    ivs = local_day_intervals(date(2025, 10, 26), "PT15M")
    assert ivs[8].start != ivs[12].start   # 02:00 CEST vs 02:00 CET
    assert interval_for_index(date(2025, 10, 26), 9, "PT15M") == ivs[8]

def test_start_vs_end_label():
    ts = datetime(2026, 9, 17, 0, 0, tzinfo=ZoneInfo("Europe/Prague"))
    assert interval_from_timestamp(ts, "PT15M", "start").start == ts.astimezone(UTC)
    assert interval_from_timestamp(ts, "PT15M", "end").end == ts.astimezone(UTC)

def test_naive_timestamp_rejected(): pytest.raises(ValueError, interval_from_timestamp, datetime(2026,1,1), "PT15M", "start")
def test_bad_duration(): pytest.raises(ValueError, parse_duration, "15min")
```
- [ ] **Step 2:** run `uv run pytest tests/contracts/test_intervals.py -q` → ImportError.
- [ ] **Step 3:** implement; **Step 4:** tests pass; `make check` green.
- [ ] **Step 5: Commit** `feat(contracts): delivery intervals — DST-safe local-day tiling, index and label mapping (ADR-011, 01 §7)`.

### Task 1.4 — `decimals.py` with property tests

**Files:** create `energy_platform/contracts/decimals.py`, `tests/contracts/test_decimals.py`.

**Produces:**
```text
Separator = Literal["dot", "comma"]
Sign = Literal["as_published", "inverted"]
def parse_decimal(text: str | Decimal | int | None, separator: Separator) -> Decimal | None
    # None / "" / whitespace → None; Decimal/int pass through; str: strip, reject any char outside [0-9+-] + the one separator (thousands separators, NaN, Inf, 'e' → ValueError); comma → replace once with '.'; Decimal(...)
def apply_sign(value: Decimal | None, sign: Sign) -> Decimal | None   # inverted → -value; None → None; -0 normalised to 0
```

- [ ] **Step 1: tests**
```text
@given(st.decimals(allow_nan=False, allow_infinity=False, places=3, min_value=-10**6, max_value=10**6))
def test_comma_roundtrip(d): assert parse_decimal(str(d).replace(".", ","), "comma") == d
@given(same) def test_dot_roundtrip(d): assert parse_decimal(str(d), "dot") == d
@pytest.mark.parametrize("text", ["1,234.5", "1.234,5", "NaN", "inf", "1e3", "12 345", "abc"])
def test_rejects_ambiguous(text): pytest.raises(ValueError, parse_decimal, text, "dot")
def test_blank_is_null(): assert parse_decimal("  ", "dot") is None and parse_decimal(None, "comma") is None
def test_dot_text_under_comma_rule_is_rejected(): pytest.raises(ValueError, parse_decimal, "170.13", "comma")
def test_no_float_precision_loss(): assert parse_decimal("0,1", "comma") + parse_decimal("0,2", "comma") == Decimal("0.3")
@given(st.decimals(allow_nan=False, allow_infinity=False, places=3))
def test_inversion_is_involution(d): assert apply_sign(apply_sign(d, "inverted"), "inverted") == d
def test_sign_of_none(): assert apply_sign(None, "inverted") is None
```
- [ ] **Step 2–4:** fail → implement → pass; `make check`.
- [ ] **Step 5: Commit** `feat(contracts): explicit decimal-separator parsing and sign convention (ADR-019, 01 §9)`.

### Task 1.5 — registries: `registry.py`, `hosts.py`

**Files:** create `energy_platform/contracts/registry.py`, `energy_platform/contracts/hosts.py`, `tests/contracts/test_registry.py`, `tests/contracts/test_hosts.py`; modify `CODEOWNERS` (explicit lines for both files).

**Produces:**
```text
SignRule = Literal["negative_allowed", "non_negative", "non_negative_expected"]
@dataclass(frozen=True) class MetricSpec: name: str; unit: str; currency: str | None; sign: SignRule; null_meaning: str; owner_transport: str | None = None
@dataclass(frozen=True) class DatasetContract:
    dataset_id: str; source_id: str; contract_version: str  # semver
    identity_key: tuple[str, ...]           # 01 §6.3 order
    fixed_dimensions: Mapping[str, str]     # e.g. {"bidding_zone": "CZ"}
    metrics: Mapping[str, MetricSpec]
    resolutions: tuple[str, ...]            # declared by the source: ("PT15M", "PT60M")
    def metric(self, name) -> MetricSpec | None
DATASETS: Mapping[str, DatasetContract]     # ote.idm_continuous, ote.dam, ceps.load — nothing else
def dataset(dataset_id: str) -> DatasetContract | None

@dataclass(frozen=True) class HostEntry: host: str; ports: tuple[int, ...] = (443,); allow_insecure: bool = False; note: str = ""
HOSTS: Mapping[str, HostEntry]              # www.ote-cr.cz, www.ceps.cz
def host(name: str) -> HostEntry | None     # exact, case-insensitive match; no wildcards
```
Seed values (from 01 §3/§6.3/§9):
- `ote.idm_continuous`: key `(bidding_zone, delivery_start_utc, resolution)`, fixed `{bidding_zone: CZ}`, metrics `price_vwap` EUR/MWh EUR negative_allowed "no trade in period, or not yet published" owner `soap`; `volume_total` MWh non_negative "not yet published" owner `soap`; `volume_buy`, `volume_sell` MWh non_negative owner `xlsx`; `price_min`, `price_max`, `price_last` EUR/MWh negative_allowed owner `xlsx`; resolutions `(PT15M, PT60M)`.
- `ote.dam`: same key; metrics `price`, `price_hourly` EUR/MWh negative_allowed "no result"; `volume_total` MWh non_negative "no result"; `emergency_state` unit `1` (dimensionless flag) non_negative "no result"; resolutions `(PT15M, PT60M)`.
- `ceps.load`: key `(area, delivery_start_utc, resolution, aggregation_function, version)`, fixed `{area: CZ}` (aggregation_function is a constant supplied by the manifest, checked ∈ {AVG}; version bound to `source_version`, P1-D2); metrics `load_incl_pumping`, `load` MW non_negative_expected "missing sample"; resolutions `(PT15M,)`.
- Candidates from 01 §6.3 are **not** registered (Route B).

- [ ] **Step 1: tests** — each committed dataset present with the exact identity key tuple and metric names from 01 §6.3; `dataset("ote.imbalance_settlement") is None`; every metric unit ∈ {"EUR/MWh","MWh","MW","1"}; `host("www.ote-cr.cz").ports == (443,)`; `host("WWW.OTE-CR.CZ")` resolves; `host("web-api.tp.entsoe.eu") is None`; no registry entry has `allow_insecure=True`.
- [ ] **Step 2–4:** fail → implement → pass; `make check`.
- [ ] **Step 5: Commit** `feat(contracts): dataset and host registries seeded from 01 §3/§6.3/§9 (ADR-022, ADR-026)`.

### Task 1.6 — `observation.py`

**Files:** create `energy_platform/contracts/observation.py`, `tests/contracts/test_observation.py`.

**Produces:** (Pydantic `BaseModel`, `frozen=True`, `extra="forbid"`)
```text
class EnergyObservation(BaseModel):
    # envelope — 01 §6.1 + ADR-023
    source_id: str; dataset_id: str; source_transport: Literal["soap","xlsx","html","rest"]
    contract_version: str; derivation_id: str  # 16 hex
    raw_ref: str; payload_sha256: str          # 64 hex
    fetched_at: AwareDatetime; source_published_at: AwareDatetime | None; source_version: str | None; processed_at: AwareDatetime
    # time — 01 §6.2
    delivery_interval: DeliveryInterval; resolution: str; local_date: date; period_index: int | None; kind: Literal["interval","point"]
    # identity + value — 01 §6.3 / §9 (P1-D1)
    dimensions: Mapping[str, str]; metric: str; value: Decimal | None; unit: str; sign_convention: Sign
    @property delivery_start_utc / delivery_end_utc
    validators: dataset_id ∈ DATASETS; metric ∈ dataset.metrics and unit == registry unit; dimensions keys == identity_key − {delivery_start_utc, resolution, version}; fixed dims match; interval length == parse_duration(resolution) when kind == interval; all datetimes converted to UTC on validation
def observation_identity(o) -> tuple: (dataset_id, sorted dims items, delivery_start_utc, resolution, metric, source_version)
def version_identity(o) -> tuple: observation_identity(o) + (payload_sha256, derivation_id)
def derivation_id(platform_version: str, contract_version: str, mapping_block: Mapping[str, Any], parser_ref: str) -> str
    # sha256(json.dumps({...}, sort_keys=True, separators=(",",":"), ensure_ascii=False)).hexdigest()[:16]
```
- [ ] **Step 1: tests** — a valid T1 row (2026-09-17 period 1, `price_vwap` 170.13) builds; naive `fetched_at` rejected; `unit="MW"` for `price_vwap` rejected with a message naming the registry unit; unknown metric rejected; unregistered `dataset_id` rejected; wrong dimension key rejected; interval/resolution mismatch rejected; `version_identity` differs when only `derivation_id` differs and when only `payload_sha256` differs; equal for a byte-identical retry; `source_version=None` is part of the identity (two rows with None compare equal); `derivation_id` is 16 lowercase hex, stable under key order of `mapping_block`, changes with `parser_ref`.
- [ ] **Step 2–4:** fail → implement → pass; `make check`.
- [ ] **Step 5: Commit** `feat(contracts): EnergyObservation with observation/version identity and derivation_id (ADR-018, ADR-023)`.

### Task 1.7 — `parser.py`

**Files:** create `energy_platform/contracts/parser.py`, `tests/contracts/test_parser.py`.

**Produces:** (frozen dataclasses; no third-party import so a target's `parser.py` can import them)
```text
Cell = str | Decimal | int | bool | None
@dataclass(frozen=True) class TabularDocument: kind: Literal["csv","html-table"]; header: tuple[str, ...]; rows: tuple[tuple[Cell, ...], ...]
@dataclass(frozen=True) class SheetsDocument: kind: Literal["xlsx"] = "xlsx"; sheets: Mapping[str, tuple[tuple[Cell, ...], ...]]
@dataclass(frozen=True) class XmlElement: tag: str; attrib: Mapping[str, str]; text: str | None; children: tuple["XmlElement", ...]
    def find_all(self, tag) -> tuple[XmlElement, ...]   # depth-first, local-name match (namespace stripped)
    def first(self, tag) -> XmlElement | None
@dataclass(frozen=True) class XmlDocument: kind: Literal["xml","soap"]; root: XmlElement
JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
@dataclass(frozen=True) class JsonDocument: kind: Literal["json"] = "json"; data: JsonValue
DecodedDocument = TabularDocument | SheetsDocument | XmlDocument | JsonDocument
DecodeKind = Literal["xlsx","xml","soap","json","html-table","csv"]
@dataclass(frozen=True) class SourceRecord: fields: Mapping[str, Cell]; locator: str   # locator = "row 7" / "item[3]" for quarantine messages
class Parser(Protocol): def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]: ...
```
- [ ] **Step 1: tests** — a toy class with `parse()` satisfies `Parser` (runtime_checkable); `XmlElement.find_all("Item")` finds namespaced `{ns}Item`; `SourceRecord` is hashable/frozen; the module imports nothing outside stdlib (`ast`-based assertion, mirroring `scripts/check_target_surface.py` PARSER_STDLIB ∪ {"__future__", "collections.abc"}).
- [ ] **Step 2–4:** fail → implement → pass; `make check`.
- [ ] **Step 5: Commit** `feat(contracts): Parser protocol over platform-decoded documents (ADR-027 §2)`.

### Task 1.8 — `manifest.py`: model, loader, structural + admission validation

**Files:** create `energy_platform/contracts/manifest.py`, `tests/contracts/test_manifest.py`, `tests/contracts/test_manifest_negative.py`; modify `energy_platform/contracts/__init__.py` (re-exports).

**Produces:** (all Pydantic v2, `frozen=True`, `extra="forbid"`)
```text
Modality = Literal["soap-xml","dated-file","html-table","rest-json","rest-xml"]
class SecretRef(BaseModel): name: str; key: str
class Auth(BaseModel): secretRef: SecretRef; location: Literal["query","header"]; param: str   # ENTSO-E: query securityToken
class RateLimit(BaseModel): requests: PositiveInt; per: str   # ISO duration
class Discovery(BaseModel): url: HttpUrl; link_regex: str          # T2: page → .xlsx link
class SoapXmlFetch(BaseModel): url: HttpUrl; soap_action: str; body_template: str; params: Mapping[str, str]   # params values are template expressions like "{delivery_day:%Y-%m-%d}"
class DatedFileFetch(BaseModel): discovery: Discovery | None; url_template: str; file_format: Literal["xlsx","csv"]
class HtmlTableFetch(BaseModel): url: HttpUrl; table_selector: str
class RestJsonFetch(BaseModel): url_template: str; query: Mapping[str, str]; auth: Auth | None; headers: Mapping[str,str] = {}
class RestXmlFetch(BaseModel): url_template: str; query: Mapping[str, str]; auth: Auth | None; rate_limit: RateLimit
class FetchBlock(BaseModel): soap_xml | dated_file | html_table | rest_json | rest_xml — all Optional; validator: exactly one set
class Cadence(BaseModel): cron: str (5 fields, validated by regex); timezone: str (ZoneInfo must resolve)
class History(BaseModel): max_age: str   # ISO duration or "none"
class Contract(BaseModel): dataset_id: str; metrics: tuple[str, ...] (non-empty, unique); decode: DecodeKind; source_transport: Literal["soap","xlsx","html","rest"]
class FieldRef(BaseModel): source: str | None; constant: str | None  — exactly one
class TimeMapping(BaseModel): timezone: str; kind: Literal["period_index","timestamp"]; date: FieldRef|None; index: FieldRef|None; resolution: FieldRef; timestamp: FieldRef|None; interval_label: Literal["start","end"] = "start"; validator: period_index needs date+index; timestamp needs timestamp
class MetricMapping(BaseModel): source: str; unit: str; sign: Sign = "as_published"; decimal_separator: Separator = "dot"
class Mapping_(BaseModel, alias "mapping"): dimensions: Mapping[str,str]; time: TimeMapping; source_version: FieldRef | None; source_published_at: FieldRef | None; metrics: Mapping[str, MetricMapping]
class Manifest(BaseModel):
    schema_version: Literal[1]; target_id: str (^[a-z][a-z0-9_]{2,63}$); description: str = ""
    license: str (min 1); terms_url: HttpUrl; allowed_hosts: tuple[str, ...] (non-empty, lowercase hostnames)
    allow_insecure: bool = False; modality: Modality; cadence: Cadence; history: History
    fetch: FetchBlock; contract: Contract; mapping: Mapping_
    structural validators: fetch key matches modality; every URL/url_template host ∈ allowed_hosts; scheme https unless allow_insecure; no string anywhere in fetch matches a token pattern (AWS key id, `-----BEGIN`, `[A-Za-z0-9_-]{32,}` after `token|key|secret|password` ≈ the regexes of scripts/secret_scan.py, duplicated here because platform code must not import scripts/); contract.metrics == mapping.metrics keys; contract.source_transport consistent with modality (soap-xml→soap, dated-file→xlsx, html-table→html, rest-*→rest)
    def mapping_block(self) -> dict[str, Any]   # model_dump(mode="json") of mapping — the ADR-023 hash input

class ManifestSyntaxError(ValueError)   # anchors/aliases/tags/merge keys/multi-doc
def load_manifest(path: Path) -> Manifest      # yaml.safe_load after scanning tokens: AliasToken/AnchorToken/TagToken → ManifestSyntaxError; >1 document → error
class AdmissionGaps(BaseModel): datasets: tuple[str,...]; metrics: tuple[tuple[str,str],...]; hosts: tuple[str,...]; insecure_hosts: tuple[str,...]
class ValidationResult(BaseModel): status: Literal["OK","INVALID","ADMISSION_REQUIRED"]; errors: tuple[str,...]; missing: AdmissionGaps
def validate_manifest(m: Manifest) -> ValidationResult
    # ADMISSION_REQUIRED when: dataset_id ∉ DATASETS; a metric ∉ dataset.metrics; a host ∉ HOSTS; allow_insecure requested but registry entry says False
    # INVALID when registered but inconsistent: metric unit ≠ registry unit; dimensions keys/values ≠ registry identity key/fixed dims; time.resolution constant ∉ dataset.resolutions; ceps-style `version` in identity key but mapping.source_version is None
    # OK otherwise. ADMISSION gaps are reported *together with* INVALID errors; status precedence: ADMISSION_REQUIRED > INVALID > OK
```
- [ ] **Step 1: positive tests** (`test_manifest.py`) — a minimal T1 manifest dict validates; `mapping_block()` is JSON-serialisable and key-order-stable; `load_manifest` on a temp file works; `validate_manifest` → `OK`.
- [ ] **Step 2: negative tests** (`test_manifest_negative.py`), one per roadmap row plus ADR-017: missing `license` → `ValidationError`; `terms_url` missing; `allowed_hosts` empty; url host not in `allowed_hosts`; `http://` without `allow_insecure` → error names `allow_insecure`; `fetch` with two keys; `fetch.soap_xml` under `modality: html-table`; token-looking string in `fetch` → error names "secret"; YAML with an anchor/alias → `ManifestSyntaxError`; YAML with a `!!python` tag → `ManifestSyntaxError`; two documents → error; unregistered `dataset_id` → `ADMISSION_REQUIRED` with `missing.datasets == ("x.y",)`; unregistered metric → `missing.metrics == (("ote.idm_continuous","price_median"),)`; host not in registry → `missing.hosts`; `allow_insecure: true` on `www.ote-cr.cz` → `missing.insecure_hosts`; unit mismatch → `INVALID` with an error naming both units; dimension `bidding_zone: DE` → `INVALID`; the result `model_dump()` has exactly the keys `status`, `errors`, `missing` (ADR-022 §2 shape).
- [ ] **Step 3–4:** fail → implement → pass; `make check`.
- [ ] **Step 5: Commit** `feat(contracts): manifest model, loader and two-stage validation with ADMISSION_REQUIRED (ADR-017, ADR-022, ADR-026)`.

### Task 1.9 — JSON Schema export

**Files:** create `scripts/export_manifest_schema.py`, `schemas/manifest.v1.json`, `tests/contracts/test_schema_export.py`; modify `Makefile` (`schema` target; `lint` does **not** regenerate).

- [ ] **Step 1: test** — `Manifest.model_json_schema()` rendered with `json.dumps(..., indent=2, sort_keys=True) + "\n"` equals the committed file byte for byte (message: "run `make schema`"); schema `title == "Manifest"`, `$schema` present (add via `json_schema_extra`), `properties.schema_version.const == 1`, `required` contains license/terms_url/allowed_hosts/cadence/modality/fetch/mapping/contract/history.
- [ ] **Step 2:** script prints the rendering; `make schema` writes it: `$(RUN) python scripts/export_manifest_schema.py > schemas/manifest.v1.json`.
- [ ] **Step 3:** run `make schema`, test passes, `make check` green.
- [ ] **Step 4: Commit** `feat(contracts): export schemas/manifest.v1.json from the Pydantic model (ADR-017)`.

### Task 1.10 — six example manifests

**Files:** create `examples/manifests/README.md` and six YAML files; `tests/contracts/test_examples.py`.

| File | Modality | Source | Expected `validate_manifest` |
|---|---|---|---|
| `ote_idm_soap.yaml` | soap-xml | T1 `GetImPricePeriodE`, host `www.ote-cr.cz`, decode `soap`, transport `soap`, metrics `price_vwap`, `volume_total`; time `period_index` from `Date`/`PeriodIndex`/`PeriodResolution`; `history.max_age: P31D`... **no**: 01 §3 says >31 days per call, coverage from 2024-07-01 → `max_age: none` is wrong too; use `P2Y` with a comment `[UNVERIFIED] coverage, 01 §3` | OK |
| `ote_idm_xlsx.yaml` | dated-file | T2: discovery page + fallback `url_template`, decode `xlsx`, transport `xlsx`, five T2 metrics + the two shared ones (stored, reconciled per 01 §3 rule 2); time from `Period` with constant `PT15M`; `max_age: P1Y` [UNVERIFIED] | OK |
| `ceps_load_soap.yaml` | soap-xml | T3 `Load`, host `www.ceps.cz`, decode `soap`; time `timestamp` from `@date`, `interval_label: start` with the F13 `[UNVERIFIED]` comment; dimensions `{area: CZ, aggregation_function: AVG}`; `source_version: {constant: RT}`; metrics `load_incl_pumping`←`value1`, `load`←`value2`; `max_age: P1Y` [UNVERIFIED] | OK |
| `ote_idm_html_table.yaml` | html-table | shape-only: the OTE results page (S02) rendering the same table with a **decimal comma**; registered dataset/host; `decimal_separator: comma` | OK (registered) |
| `token_api_rest_json.yaml` | rest-json | shape-only: token-keyed JSON API (`auth.secretRef`, `location: query`), host `api.example.invalid`, dataset `example.rest_json`, metrics `value` | ADMISSION_REQUIRED (dataset, metric, host) |
| `entsoe_rest_xml.yaml` | rest-xml | shape-only, P1-D5: ENTSO-E `web-api.tp.entsoe.eu/api`, `documentType=A44`, `securityToken` via `secretRef`, `rate_limit: {requests: 400, per: PT1M}`, dataset `entsoe.day_ahead_prices` | ADMISSION_REQUIRED (dataset, metric, host) |

- [ ] **Step 1: test** — parametrised over the six paths: `load_manifest` succeeds; `jsonschema`-free structural check = Pydantic; expected status per table; the three real ones' `missing` is empty; every modality value appears at least once across the six; every decode kind except `csv`/`json`... (assert the set of decode kinds used ⊇ {soap, xlsx, html-table, xml, json}).
- [ ] **Step 2:** write the manifests (real values from 01 §3; comments cite S-refs and mark `[UNVERIFIED]`); README explains P1-D4 and that nothing here is fetched.
- [ ] **Step 3:** tests pass; `make check` green (ruff does not lint YAML; `check_target_surface` does not scan `examples/`).
- [ ] **Step 4: Commit** `feat(contracts): six example manifests — T1, T2, T3 admitted; three shape-only return ADMISSION_REQUIRED`.

### Task 1.11 — close the phase

**Files:** modify `docs/03-roadmap.md` (Phase 1 checkboxes; P1-D5 wording), `docs/progress.md`, `docs/04-contracts.md` (reconcile against the code as built), memory.

- [ ] **Step 1:** re-read 04-contracts.md against the shipped models; fix drift.
- [ ] **Step 2:** tick every Phase 1 box; correct the ENTSO-E parenthetical; append the dated progress entry (done / learned / next = Phase 2 starter prompt verbatim).
- [ ] **Step 3:** `make check` green; `make deps-allowlist`, `make secret-scan` green.
- [ ] **Step 4: Commit** `docs(roadmap): Phase 1 done — contracts package, schema, six example manifests`.

## Verification before each commit

`make check` (lint + lock-check + type + test). Tasks 1.1 and 1.11 also run `make deps-allowlist` and `make secret-scan`.

## Stop conditions

- A deliverable needs a field 01 does not name → stop; record in 04 §5 as a Route B question, do not add it.
- A needed dependency is outside ADR-019/ADR-029 → stop, propose an ADR.
- Any test would need the network → it does not belong in this phase.

## Self-review (done while writing)

- Spec coverage: every Phase 1 checkbox maps to a task (ADRs → 1.1/1.2; 04-contracts → 1.2/1.11; observation → 1.6; registry/hosts → 1.5; manifest → 1.8/1.9; parser → 1.7; six manifests → 1.10; property tests → 1.3/1.4; negative tests → 1.8).
- Names used across tasks: `DeliveryInterval`, `parse_duration`, `Sign`, `Separator`, `DATASETS`, `HOSTS`, `MetricSpec`, `DatasetContract`, `HostEntry`, `DecodedDocument`, `SourceRecord`, `Parser`, `Manifest`, `ValidationResult`, `AdmissionGaps`, `validate_manifest`, `load_manifest`, `derivation_id` — consistent.
