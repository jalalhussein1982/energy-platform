# Plan — Phase 2: Platform core library (2026-09-20)

> **For agentic workers:** execute task by task. One task = one commit, `make check` green before
> each commit (03 §0). Steps use `- [ ]` checkboxes.

| | |
|---|---|
| Goal | The platform owns semantics end to end, runnable locally on fixtures. Gate: `make demo` runs fixture → capture → Bronze → parse → map → Postgres → query, offline; every migration has a downgrade exercised by a Make target that CI calls. |
| Spec | `docs/03-roadmap.md` Phase 2; `docs/02-architecture-decisions.md` ADR-002, ADR-004, ADR-005, ADR-010; `docs/adr/` ADR-003 rev., ADR-016, ADR-018, ADR-019, ADR-021, ADR-023, ADR-024, ADR-026, ADR-027, ADR-029; `docs/04-contracts.md`; `docs/01-data-scope.md` §3, §5, §7, §9. |
| Architecture | `energy_platform/` gains `fetch/`, `bronze/`, `parse/`, `mapping/`, `silver/`, `ledger/`, `runtime/`, `cli.py`. Contracts stay pure data. Persistence is behind one `Store` protocol with a memory implementation (unit tests, the ADR-023 proofs, the ADR-024 crash matrix) and a Postgres implementation (demo, `db`-marked tests). Bronze is behind `BlobStore`/`CaptureLog` protocols with memory and filesystem backends. |
| Tech | Runtime (ADR-019): `httpx`, `lxml`, `openpyxl`, `psycopg` v3, `alembic` + `sqlalchemy` (Alembic's engine only), `typer`. Stubs (ADR-029): `lxml-stubs`, `types-openpyxl`. Nothing else. |
| Do not | Create anything under `targets/`. Fetch from the network in a test. Edit docs/00, 01, 02. Weaken a gate. Add Kubernetes material. Decide S3 client library without an ADR (P2-D4). |

## Global constraints (copied from the spec)

- Order of a run is `FETCH → WRITE RAW → ACKNOWLEDGE CAPTURE → PROCESS`; the durable boundary is Bronze (blob + capture-log entry), the ledger is an index written after and rebuilt by `reconcile` (ADR-004, ADR-024 §1–2).
- Ledger: `runs` one per `(target_id, scheduled_for)` with `state ∈ {scheduled, captured, processed, failed, missing_capture, unrecoverable}`, `fence`, `origin`, latest lease; `run_attempts` one per attempt with `kind ∈ {capture, process, backfill, replay}`, lease, `fence`, `capture_id`, `derivation_id`, `outcome`, `error`; fencing at commit: every Silver write and state transition executes in one transaction predicated on `runs.fence = $my_fence`; a stale holder affects zero rows and exits `lost_lease` (ADR-024 §3–4).
- Version identity = observation identity ⊕ `payload_sha256` ⊕ `derivation_id`; NULL `source_version` is a value (`NULLS NOT DISTINCT`); current view by ordering basis (`source_published_at` else capture `fetched_at`), then `contract_version` semver, then `derivations.registered_at`, then `derivation_id`; nothing updated in place (ADR-023).
- Three verbs: `capture` fetches on schedule; `backfill` fetches a period with no capture-log entry, only within `history.max_age`; `replay` never fetches (ADR-024 §5).
- Fetch (ADR-026 §2): `https` only unless `allow_insecure` on manifest **and** registry; host ∈ manifest `allowed_hosts` **and** registry; resolve the name, reject private/metadata/loopback/CGNAT ranges, re-check the connected peer; redirects followed by the fetch layer only, ≤ `max_redirects` (3), every hop validated; ports from the registry; proxy env honoured.
- Bronze layout (ADR-002, ADR-024): `bronze/blobs/<sha[:2]>/<sha>`; `captures/<target_id>/<YYYY>/<MM>/<DD>/<scheduled_for>_<attempt>.json`; entry fields follow 01 §6.1 names plus `capture_id`, `content_changed`, `tier` (ADR-021); read path tries hot then cold.
- Values: `decimal.Decimal` under the declared separator; blank/absent → NULL; quarantine on the 01 §9 causes; MW vs MWh from the registry (04 §2.8).
- Every migration ships a downgrade (ADR-016 §3). Plain PostgreSQL ≥ 16 (ADR-030). Gap detector per ADR-031.
- Unit tests run with sockets disabled; nothing here is `live`. Tests that need a local PostgreSQL are marked `db`, skip without `ENERGY_PLATFORM_TEST_DSN`, and run through `make db-test`.

## Decisions taken by this plan (formalisations, not new policy)

| # | Decision | Why |
|---|---|---|
| P2-D1 | D-2 engine: plain PostgreSQL ≥ 16, no extension — **ADR-030**. | Schema is created in this phase; the DSN contract must hold on all three `postgres.mode`s. |
| P2-D2 | D-4 defaults (cron-evaluated expected instants, tolerance 2× cadence, classification order, Bronze as truth) — **ADR-031**. | 03 §0 rule 5: default implemented only after its ADR exists. |
| P2-D3 | One `Store` protocol covers ledger, derivations, Silver rows and quality events; `MemoryStore` and `PostgresStore` implement it; the six ADR-023 proofs and the ADR-024 crash matrix are one parametrised suite that runs on both. | Fencing couples Silver writes to ledger state in one transaction (ADR-024 §4); splitting the interfaces would hide that coupling. |
| P2-D4 | Bronze backends in this phase: **memory** and **filesystem directory**; the S3/MinIO backend is deferred to a PROPOSED **ADR-032** (client library: `boto3` or SigV4 over `httpx` inside `fetch/`) because neither is in ADR-019 and outbound HTTP outside `fetch/` is banned (ADR-027 §3). The tiered read path and `tier` field are implemented over the protocol. | No dependency without an ADR (CLAUDE.md); the choice is a human's. |
| P2-D5 | Generic parsers are constructed by the platform from the manifest: a record is an XML element / sheet row / table row / JSON object that supplies every **time** source field and every `source`-typed `source_version` / `source_published_at` field; metric fields absent from a record become NULL. Elements that echo the request (ČEPS `information`) are not records because they lack the time field. | Keeps the manifest schema unchanged (no parser-configuration block) and matches 01 §3: OTE `Price`/`Volume` are optional. |
| P2-D6 | Quarantine causes: a mapped header/field missing from every record (changed header, changed unit label), a mapped cell that is not a decimal under the declared separator, a non-finite value, a `non_negative` violation, a SOAP `Fault`, an undecodable payload, no record at all when the document is not the documented empty `<Result/>` shape. Fields present in the document but not referenced by the mapping raise the quality event `unknown_field` (warning), **not** a quarantine. | The frozen manifest cannot enumerate display-only columns (T2 `Time interval`); escalating `unknown_field` to quarantine needs a manifest field (`mapping.ignore_fields`) → recorded as an ADR question in 04 §5, not decided here. |
| P2-D7 | `non_negative_expected` violation → quality event `negative_value` (row stored); completeness per delivery day (01 §5 `partial`/`complete`, 92/96/100 expected) → quality event `partition_status`; T1/T2 reconciliation (01 §3 rule 2) → `reconciliation_mismatch` above 0.01 EUR/MWh or 0.001 MWh, both directions, computed against the current view after the upsert. | 01 §3, §5, §9 as written. |
| P2-D8 | No custom `parser.py` loading in this phase; `parser_ref` is always `generic:<decode>@<platform_version>`. The loader is a Phase 3 deliverable (one CODEOWNERS module; dynamic import is banned platform-wide by ADR-027 §3 and needs its own lint exception recorded there). | No target exists before Phase 3 (03 "harness before code"). |
| P2-D9 | `energyctl` commands take `--manifest <path>` in this phase; `<id>` resolution against `targets/` arrives with the Phase 3 scaffolder. Output through `typer.echo` (library code keeps the `T20` rule). | Same reason. |
| P2-D10 | Peer-address re-check: the connected peer reported by the transport must be one of the addresses the fetch layer resolved; a transport that reports no peer (fixtures, mocks) is accepted only when the caller passes `offline=True`, which the CLI does for `--fixture` captures and `demo`. | ADR-026 §2 "re-checks the connected peer address"; fixtures never touch the network. |
| P2-D11 | Pending work in the ledger: a run is claimable for processing when `state = captured` or when it has a `replay` attempt with `outcome IS NULL`; a replay never changes the `state` of a `processed` run. `replay --derivation <bad>` enqueues one pending replay attempt per capture that has a Silver row with that derivation. | ADR-023 §4, ADR-024 §3 without a new state. |
| P2-D12 | `history.max_age` (`P2Y`, `P1Y`, `P31D`, `PT48H`, `none`) is applied with calendar year/month arithmetic in `Europe/Prague`, day clamped; no `dateutil`. | Only `intervals.parse_duration` exists and rejects months/years on purpose. |
| P2-D13 | Local PostgreSQL for `make demo` and `make db-test`: `scripts/ephemeral_postgres.sh` starts `initdb`/`pg_ctl` on a Unix socket in a scratch directory (offline) unless `ENERGY_PLATFORM_DSN` is set; the Makefile convention holds (binaries missing while migrations exist → fail, never fake a pass). | ADR-010 offline demo; ADR-016 §3 downgrade exercised in CI (`ubuntu-latest` ships PostgreSQL 16). |
| P2-D14 | Conditional requests: the capture entry records `etag` and `last_modified`; the next capture of the same target sends `If-None-Match` / `If-Modified-Since`; a `304` produces an entry with `content_changed: false` pointing at the previous blob. Backoff mechanics (4 attempts, base 0.5 s, cap 8 s, ±25 % jitter, retry on connection errors and 5xx only) are parameters; the per-target politeness **policy** stays with D-5 (Phase 4). | Phase 2 deliverable text names the mechanics; D-5 owns the values. |

## Ordered tasks

### Task 2.1 — ADRs, plan, dependencies

**Files:** `docs/adr/ADR-030-postgres-engine-plain.md`, `docs/adr/ADR-031-gap-detector-defaults.md`, `docs/adr/ADR-032-object-store-client.md` (PROPOSED), this file, `pyproject.toml`, `uv.lock`, `deps-allowlist.txt`, `docs/02-architecture-decisions.md` ADR index rows only (dated note).

- [ ] ADR-030, ADR-031 ACCEPTED; ADR-032 PROPOSED (S3 client) for the author.
- [ ] Runtime deps `httpx`, `lxml`, `openpyxl`, `psycopg`, `alembic`, `sqlalchemy`, `typer`; dev `lxml-stubs`, `types-openpyxl`; `uv lock`; every locked package listed in `deps-allowlist.txt` with its parent; `make deps-allowlist` green.
- [ ] `energy_platform.__version__ = "0.0.1"` with a test that it equals `pyproject.toml`.
- [ ] Commit `build(deps): Phase 2 runtime dependencies locked and allowlisted (ADR-019, ADR-029); ADR-030, ADR-031; plan`.

### Task 2.2 — `fetch/`

**Files:** `energy_platform/fetch/{__init__,policy,render,client,plan}.py`, `tests/fetch/`.

Produces: `render(template, ctx)` for `{delivery_day:%Y-%m-%d}` / `{scheduled_for}`; `EgressPolicy.check_url(url, manifest)` (scheme, host in manifest and registry, port, no IP literal), `check_resolved(addresses)` (private, loopback, link-local, CGNAT, metadata), `check_peer`; `Fetcher(transport, resolver, sleep, clock, offline)` with `fetch(request) -> FetchResult(url, status, headers, body, content_type, fetched_at, etag, last_modified, not_modified)`; redirects followed by hand ≤ 3 with every hop checked; retries with capped jittered backoff; conditional headers; rate limiter; `plan_for(manifest, ctx, previous)` builds the request(s) per modality: `soap_xml` (POST, SOAPAction, rendered body), `dated_file` (discovery GET + regex → download GET, fallback `url_template`), `html_table` (GET), `rest_json`/`rest_xml` (GET with query/headers; `secretRef` resolved from env `NAME_KEY` in this phase; value never logged).

- [ ] Tests (fake transport via `httpx.MockTransport`, fake resolver): host not in manifest → `host_not_allowed`; host in manifest but not registry → `host_not_registered`; `http` without both flags → `insecure_scheme`; port 8080 → `port_not_allowed`; resolves to `10.0.0.1` / `169.254.169.254` / `127.0.0.1` → `private_address`; redirect to unlisted host → `redirect_to_unlisted_host`; 4th redirect → `too_many_redirects`; 503 then 200 → one retry, backoff called with capped jitter; 404 → no retry; timeout → `fetch_error`; conditional headers sent, 304 → `not_modified`; SOAP body rendered from params; T2 discovery regex picks the link, fallback used when absent; secret resolved from env, absent from any repr/log; peer mismatch aborts; `offline=False` with no peer info aborts.
- [ ] Commit `feat(fetch): declarative fetchers with host enforcement, hand-followed redirects, capped backoff, conditional requests (ADR-026 §2)`.

### Task 2.3 — `bronze/`

**Files:** `energy_platform/bronze/{__init__,store,capture_log,bronze}.py`, `tests/bronze/`.

Produces: `BlobStore` protocol (`put(bytes)->sha`, `get(sha)`, `exists`) with `MemoryBlobStore`, `FileBlobStore(dir)`; `CaptureEntry` (Pydantic, 01 §6.1 names + `capture_id`, `target_id`, `scheduled_for`, `attempt`, `source_url`, `http_status`, `content_type`, `content_changed`, `tier`, `etag`, `last_modified`, `size`); `CaptureLog` protocol (`put`, `get`, `list(target_id, since, until)`, `latest(target_id)`) with memory and file backends; `Bronze(hot, cold, log)`: `capture(target_id, scheduled_for, result, transport, force=False) -> CaptureEntry | existing` writing blob **then** entry, attempt from listing, `content_changed` against `latest`; `read(raw_ref)` hot then cold; `write_fixture` / `load_fixture` (a fixture directory *is* a Bronze object: `blob` + `entry.json`, ADR-020).

- [ ] Tests: blob then entry order (a failing log leaves a harmless orphan blob); second capture of the same `(target, scheduled_for)` is a no-op unless `force`; `force` → attempt 2; unchanged payload → new entry, `content_changed=False`, same `raw_ref`; `304` result reuses previous blob; entry key layout; `read` falls back to cold and reports `tier`; file backend round-trips through a tmp dir; entry `payload_sha256` equals blob hash.
- [ ] Commit `feat(bronze): content-addressed blob store, capture log, hot/cold read path (ADR-002, ADR-021, ADR-024 §1)`.

### Task 2.4 — `parse/`

**Files:** `energy_platform/parse/{__init__,decode,generic,selectors}.py`, `tests/parse/` with synthetic fixtures built in-test.

Produces: `decode(payload, kind) -> DecodedDocument` (`xlsx` via openpyxl read-only, floats → `Decimal(repr)`, datetimes → ISO text; `xml`/`soap` via lxml with entities and network resolution off → `XmlElement` tree, SOAP `Fault` → `SoapFault`; `json`; `html-table` via lxml.html + a minimal CSS selector subset (tag, `#id`, `.class`, descendant); `csv`), `DecodeError`; generic parsers per P2-D5: `XmlRecordParser`, `SheetRecordParser` (header row = first row containing every required header, exact text after whitespace normalisation), `TableRecordParser`, `JsonRecordParser`, `CsvRecordParser`; `generic_parser(manifest) -> Parser` and `parser_ref(manifest)`.

- [ ] Tests: OTE `GetImPricePeriodE` response → records with `Date`, `PeriodIndex`, `PeriodResolution`, optional `Price`/`Volume` (absent → missing key), `Emerg` carried; empty `<Result/>` → zero records, no error; SOAP fault → `SoapFault`; ČEPS `Load` → `@date`, `value1`, `value2`, `information` block ignored; XLSX with title row 3, header row 6, 96 rows, footer → 96 records, footer excluded, numbers as `Decimal`; changed header `(MW)` → header not found error; html table with decimal-comma text; CSV; JSON list of objects; XXE payload does not resolve; `parser_ref` shape.
- [ ] Commit `feat(parse): platform decoders and generic record parsers for soap/xml, xlsx, html-table, csv, json (ADR-019, ADR-027 §2)`.

### Task 2.5 — `mapping/`

**Files:** `energy_platform/mapping/{__init__,engine,quality,reconcile,completeness}.py`, `tests/mapping/`.

Produces: `QualityEvent(kind, severity, message, locator)`; `Quarantined(reason, locator)`; `RunContext(target_id, scheduled_for, delivery_day, fetched_at, raw_ref, payload_sha256, processed_at)`; `map_records(manifest, records, ctx, derivation) -> MappingResult(observations, events)`: time by `period_index` (`interval_for_index`) or `timestamp` (`interval_from_timestamp` with `interval_label`), `local_date` from the interval start in the mapping timezone, `resolution` from source/constant, `source_version`/`source_published_at` from source/constant/null, metrics via `parse_decimal` + `apply_sign`, sign rules per P2-D7, P2-D6 quarantine/`unknown_field` rules; `reconcile_transports(current_rows) -> events` (P2-D7); `partition_status(observations, expected_count)`.

- [ ] Tests (Hypothesis where cheap): T1 records → 2 rows per period, values `Decimal`, interval from index; DST 92/100-row XLSX days map without error and cover the day; ČEPS `@date +02:00` `start` vs `end`; NULL never zero; decimal comma under `comma` rule; dot text under comma rule → quarantine; `Emerg` present but unmapped → `unknown_field`; changed header → quarantine; negative `volume_total` → quarantine; negative `load` → `negative_value` event, row kept; T2 `price_vwap` differing from T1 by 0.02 → `reconciliation_mismatch`, by 0.005 → none; 8 of 96 periods → `partial`, 96 → `complete`; `sign: inverted` inverts.
- [ ] Commit `feat(mapping): manifest mapping engine — intervals, decimals, sign rules, quarantine, quality events, T1/T2 reconciliation (ADR-005, 01 §3/§7/§9)`.

### Task 2.6 — `silver/` + `ledger/` store, migrations, ephemeral Postgres

**Files:** `energy_platform/store/{__init__,protocol,memory,postgres}.py` (ledger, derivations, observations, quality events — P2-D3), `energy_platform/silver/migrations/{env.py,script.py.mako,versions/0001_ledger.py,0002_silver.py}`, `energy_platform/silver/migrate.py`, `scripts/ephemeral_postgres.sh`, `Makefile` (`db-test`), `.github/workflows/ci.yml` (`db-test` job), `pyproject.toml` (`db` marker), `tests/store/`.

Produces: migrations with explicit DDL and downgrades — `derivations`, `runs`, `run_attempts`, `observations` (`tstzrange`, generated `delivery_start_utc`, `jsonb` dimensions, `UNIQUE … NULLS NOT DISTINCT` on the version identity, FK to `run_attempts`, `derivations`), `quality_events`, view `observations_current` (ADR-023 §3 ordering, `ordering_basis` column); `Store` protocol: `ensure_run`, `claim(run_id, owner, ttl) -> fence | None`, `renew`, `commit(run_id, fence, *, state, attempt_outcome, observations, events) -> CommitResult(inserted, lost_lease)` in one transaction, `start_attempt`, `pending_runs(target)`, `enqueue_replay`, `register_derivation`, `current_rows(dataset, dimensions?, start, end)`, `rows_by_derivation`, `missed_runs`; `MemoryStore` with the same semantics; `PostgresStore` with `server_version_num ≥ 160000` check; `upgrade(dsn)`, `downgrade(dsn, "base")`.

- [ ] Tests, parametrised over `memory` and `postgres` (`db`, skipped without DSN): the six ADR-023 proofs (exact retry no-op; same payload + new derivation appends and is current; older capture replayed with newer derivation is not current over a newer capture; T1/T2 ownership holds across both; NULL `source_version` retry no-op; provider correction appends); claim twice → second `None`; expired lease reclaimable, stale commit → `lost_lease`, zero rows; `ordering_basis` recorded; migration `upgrade → downgrade base → upgrade` leaves no table behind (`db` only).
- [ ] Commit `feat(store): ledger and Silver schema with downgrades, fenced commit, current view; memory and Postgres stores (ADR-018, ADR-023, ADR-024, ADR-030)`.

### Task 2.7 — `runtime/`: capture, process, reconcile, replay, backfill, gaps

**Files:** `energy_platform/runtime/{__init__,context,capture,process,reconcile,replay,backfill,gaps,cron}.py`, `tests/runtime/`.

Produces: `capture(manifest, scheduled_for, *, fetcher, bronze, store)`: plan → fetch → `bronze.capture` → `store.ensure_run(captured)` best-effort (a `StoreUnavailable` is a warning, capture stays complete); `reconcile(manifest, bronze, store, window)`; `process(manifest, *, bronze, store, clock)`: reconcile → pending runs → claim → attempt → read blob → decode → parse → map → commit (rows + events + state) fenced; quarantine → `failed`/`quarantined`; `replay(range | derivation)`; `backfill`; `gaps` per ADR-031 with the cron evaluator.

- [ ] Tests — the ADR-024 crash matrix, one each, memory backends: blob PUT then crash before entry → next run re-captures, orphan harmless; entry PUT then crash before ledger row → `reconcile` inserts `origin=reconciled`; store down during capture → capture complete, reconciled later; two workers claim → second fails; lease expires and old holder commits late → zero rows, `lost_lease`; never captured inside `max_age` → `missing_capture` + backfill run enqueued, backfill fetches and captures; outside → `unrecoverable` + alert event; replay of a capture already processed by the same derivation → no-op. Plus: cron evaluator (`*/15`, lists, ranges, DST day yields 92/100 instants for a `*/15` cadence), `max_age` calendar cutoff, `unprocessed_capture` emitted for a captured-not-processed run older than tolerance, `pending` inside tolerance.
- [ ] Commit `feat(runtime): capture, reconcile, fenced process, replay, backfill and gap detector with the ADR-024 crash matrix (ADR-003 rev., ADR-024, ADR-031)`.

### Task 2.8 — `energyctl`, fixtures, `make demo`, CI

**Files:** `energy_platform/cli.py`, `pyproject.toml` (`[project.scripts]`), `examples/fixtures/<target>/{blob,entry.json}` for T1, T2, T3 (synthetic copies of the 01 §3 shapes, generated by `scripts/make_example_fixtures.py`), `Makefile` (`demo`), `.github/workflows/ci.yml` (`demo` job), `tests/cli/`.

Produces: `energyctl validate --manifest`, `capture --manifest --scheduled-for [--fixture DIR]`, `process --manifest`, `replay --manifest (--from --to | --derivation)`, `gaps --manifest`, `backfill --manifest`, `migrate (upgrade|downgrade)`, `demo [--dsn] [--bronze-dir]`; `demo` = migrate → for T1, T2, T3: capture from fixture through the real fetch path with an offline transport → process → then a second process is a no-op, a replay with a new derivation appends → prints counts from `observations_current`, quality events, per-day completeness. `make demo` starts the ephemeral Postgres unless `ENERGY_PLATFORM_DSN` is set.

- [ ] Tests: `validate` prints the `ValidationResult` JSON with exit code by status; `demo --dsn` against memory? (no: demo is Postgres by definition — a `db` test runs `demo` end-to-end and asserts counts: T1 2×96, T2 7×96, T3 2×96 rows, zero quarantines, `partition_status = complete` for each); `capture --fixture` round-trips.
- [ ] `make demo` green here; `make check`, `make db-test`, `make deps-allowlist`, `make secret-scan` green.
- [ ] Commit `feat(cli): energyctl validate/capture/process/replay/gaps/backfill/demo; make demo runs offline on fixtures into Postgres (ADR-000, ADR-010)`.

### Task 2.9 — close the phase

- [ ] `docs/04-contracts.md` §5: add the `unknown_field` / `mapping.ignore_fields` question (P2-D6) as a Route B item; §2.8 note that quarantine rules are now enforced (`mapping/`).
- [ ] `docs/02-architecture-decisions.md`: ADR index rows for ADR-029 … ADR-032 (dated note; §4.2 D-2 / D-4 rows get a "resolved by" note). No other edit.
- [ ] Tick Phase 2 boxes in `docs/03-roadmap.md` (S3 backend box stays open with the ADR-032 pointer); append the dated `docs/progress.md` entry with the Phase 3 starter prompt.
- [ ] Commit `docs(roadmap): Phase 2 done — core library, migrations with downgrades, offline demo`.

## Verification before each commit

`make check` (lint + lock-check + type + test). Tasks 2.1, 2.6, 2.8, 2.9 also run `make deps-allowlist`, `make secret-scan`; 2.6 and 2.8 run `make db-test`; 2.8 runs `make demo`.

## Stop conditions

- A needed dependency is outside ADR-019/ADR-029 → stop, propose an ADR (done for S3: ADR-032).
- A deliverable needs a manifest field the schema does not have → record as a Route B / ADR question in 04 §5, do not add it.
- Any test would need the network → it does not belong in this phase.
