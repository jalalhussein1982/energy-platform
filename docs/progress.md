# Progress log

One dated entry per session. Newest first.

---

## 2026-09-20 — Phase 4: committed-target verification through the harness (T1, T2, T3 + E1 demo)

**Done** (`docs/plans/phase-4.md`, 7 platform commits on `main` + 4 Route A branches, `make check` green at each). **Platform, on `main`:** ADR-033 (D-5: cadence values, fetch-layer politeness as built, `cadence.correction {cron, days}` = re-capture of past delivery days with `force` — the runtime verb is Phase 5 — and a third render name `next_delivery_day` for day-ahead sources); ADR-034 (`mapping.ignore_fields`: declared display-only fields raise no `unknown_field`, a mapped name may not be ignored); an empty document is a golden outcome (`expect: {row_count: 0}`, P4-D6); schema regenerated; `docs/06-source-verification.md` (bounded live reads of every committed endpoint with time/status/size/SHA-256, terms wording, rate limits, quirks, DST patterns, 0 T1/T2 reconciliation mismatches in 346 periods, the polling-campaign procedure, the one live smoke pass); `docs/evidence/README.md` (F12: 24 rows regenerated from this session's reads; payloads outside the repo); **F13 resolved to start labelling** by HR/QH and DY/QH consistency on the live ČEPS service (interface description v3.2 obtained via the page's download endpoint; silent on the edge); the synthetic ČEPS shape aligned with the live `information` block; `docs/admissions/epex_intraday.md` (Route B refusal demo from a scratch scaffold, C-54); a scaffolder fix (units quoted — `ote.dam`'s dimensionless `"1"` came out as an int) with a regression test; the nightly live smoke (`tests/live/test_smoke.py`, `make live-smoke`, `nightly-live-smoke.yml`, CI-wrapper test now covers every workflow, 05 §2 row). **Targets, one commit each on `target/<id>` (bundle → `apply_pr_bundle`, byte-identical round trip, `make check` + `pr-surface BASE=main` green):** `ote_intraday_market` (11 fixtures/goldens incl. 92/96/100/24-item days, rolling partial by item absence, no-trade NULL, negative/zero, empty `<Result/>`, decimal comma, SOAP fault, `Emerg` ignored), `ote_intraday_market_xlsx` (9: live layout with line-break headers, blank-cell partial day, changed unit header → quarantine, extra column → warning), `ceps_load` (9: offset-aware DST days copied from live, missing attribute → NULL, negative → warning), `ote_dam` (7, **built entirely through the MCP server**: scaffold → writes → 7 offline fixtures → validate → tests → `open_pr`, with the C-48/C-49/C-50 refusals exercised and recorded in 06 §5.1). `phase-4/all-targets` = `main` + the four branches: `make check` green (681 passed, 36 goldens through `test_goldens.py`), `make live-smoke` 4 passed once. Tests on `main` 638 → 641 (+20 db, 2 live deselected).

**Formalisations recorded in the plan (P4-D1 … P4-D12):** roadmap target ids; bounded reads with local evidence; synthetic fixtures from generators kept outside the repo; PR = bundle → branch, merge is Level 3; E1 via MCP; empty-document golden; `ignore_fields`; D-5 shape; F13 method; live smoke shape-only; EPEX as admission request; campaign defined not run.

**Learned.** The harness works as a workload but had three gaps a target author hits immediately: no way to expect an empty document, no way to declare a display-only column, and a scaffold that its own model refuses for a dimensionless unit — each fixed on `main` with a test. Reading golden values back from the blob caught three values I had typed from a formula (T1 periods 9/12/13); the values must come from the fixture, never from the head. Branch switching leaves `__pycache__` skeletons under `targets/<id>/`, and the surface check then reports a target without a manifest — `find targets -name __pycache__ -exec rm -rf` before `make check`. `git checkout` of a branch also leaves an empty `targets/<id>/tests/golden/` tree; `find targets -type d -empty -delete`. `apply_pr_bundle` demands a clean tree, so an untracked doc must be committed (or the target moved aside) first. Unquoted heredocs eat backticks in YAML comments; zsh does not word-split `$f` in `set -- $f`. `make fixtures` is not byte-deterministic for the XLSX example (openpyxl core properties). MCP `record_fixture` confines `payload_path` to the repository: stage payloads under the git-ignored `.energy_platform/`. Aware-datetime `+ timedelta` in a ZoneInfo zone walks the wall clock, so DST-day tiling must come from `local_day_intervals`; the platform quarantined the wrong fixture as a duplicate identity, which is the right behaviour.

**Open / carried.** Merge of the four `target/*` branches into `main` (Level 3, maintainer). One-week polling campaign (06 §6) not run; no latency figure. Phase 5 inherits: `energyctl recapture` + second CronJob from `cadence.correction` (ADR-033), the `license: restricted` refusal in the CronJob renderer, `{next_delivery_day}` in the rendered E1 job, and the process verb's handling of a forced re-capture. OTE/ČEPS redistribution and ČEPS service terms (01 §10, V-1/V-3), OTE 15-minute polling confirmation, ČEPS `value1 = value2` question (06 §4.2), custom `parser.py` loader (05 §5), V-12 … V-14, F09/F12-ledger as before.

**Next prompt** (03 Phase 5 starter, verbatim):

```text
Read CLAUDE.md, docs/00-assumptions.md, docs/02-architecture-decisions.md (ADR-001 to ADR-004, ADR-012, ADR-016), docs/adr/ (ADR-028 for the demo environment), docs/03-roadmap.md Phase 5. Confirm V-12, V-13, V-14 are filled in `00` §5; if not, stop and ask the author to run them. Write the D-* ADRs first. Then build the Helm chart and local profile until `make local-up && make smoke-test` passes from a clean clone; then the own-cluster Terraform roots (`openstack` mock-tested, `hcloud` planned — the author applies); then deploy the tenant values into the demo cluster's namespace; then backups, the cross-provider Bronze replication, the restore drill and the rollback drill; then observability. Never apply Terraform, never delete a bucket, never leave a release on the reference cluster. Stop when all gates pass.
```

---

## 2026-09-20 — Phase 3: harness (constraint matrix, scaffolder, MCP server, CI gates, negative tests)

**Done** (`docs/plans/phase-3.md`, 7 commits, `make check` green at each). `docs/05-constraint-matrix.md` written first: 54 rows (C-01…C-54) in five groups — target authoring, manifest/registry, egress, repository/supply chain, agent tooling — each with a mechanical gate and a named negative test; every roadmap-mandated row is present and `tests/harness/test_matrix.py` fails when a cited test or Make target stops existing. `energy_platform/harness/`: `surface.py` (the ADR-027 checker moved from `scripts/` into the library, plus new rules: hardcoded URL, `float()`, `while True`, placeholder tokens, normalise-code AST rules — `* / // **`, sign flip, `astimezone`/`tzinfo=`, `timedelta` — positional integer subscripts, duplicated `energy_platform.contracts` utilities, exactly one Parser class, manifest/directory id match, completeness: Bronze fixture integrity, golden model, test module; `conftest.py` refuses an incomplete target at session start, ADR-020), `goldens.py` (offline pipeline via `runtime.process.map_payload`, identity comparison, `expect.quarantine`, `row_count`, `quality_events`; `tests/harness/test_goldens.py` auto-discovers `targets/*/tests/golden/*.yaml`), `scaffold.py` (exactly the surface; a registered dataset fills units/dimensions/resolutions; placeholders keep it from passing as a target), `fixtures.py` (`--live` through the real capture path into a scratch Bronze; `--from-file` offline), `admission.py` + `docs/admissions/TEMPLATE.md` (Route B request listing exactly the gaps), `runner.py` (goldens + in-process pytest), `pr_surface.py` (one `targets/<id>/` per PR; protected paths named — registry, hosts, allowlist, CI), `pr.py` (`open_pr` bundle, refused while any gate is red). `energy_platform/contracts/golden.py` (`GoldenFile`: rows or quarantine, `checked_by`, YAML floats refused) and a manifest rule (a `source` that is a bare column number is positional parsing). `energy_platform/mcp/`: JSON-RPC 2.0 over stdio on the standard library; tools exactly the ADR-007 eight; reads confined to the checkout with a secrets deny-list; writes only inside one target, checked by the surface rules before they are kept and rolled back otherwise, journaled; `record_fixture` live only with `--allow-network`; `open_pr` → bundle in the outbox, never a push. `scripts/apply_pr_bundle.py` (git side: verifies the bundle, branch `target/<id>` from HEAD, never `main`, push only with `--push`). Gates: `scripts/check_pr_surface.py`, `check_workloads.py` (action pins to 40-hex, image digests in Kubernetes YAML and Dockerfiles, requests/limits on every container incl. init containers), `check_migrations.py` (real `downgrade()`, linear chain); Make `validate-targets`, `migration-check`, `workload-check`, `harness-check` (now part of `check`), `pr-surface` (honest skip without a base), `new-target`; CI jobs `harness-check` and `pr-surface` (base SHA from the PR event); `helm-lint` will feed the rendered chart to the workload checker. `energyctl`: `validate [ID|--all|-m]`, `new-target`, `record-fixture`, `run-target-tests`, `admission-request`, `pr-bundle`, `mcp-serve`. `deployment/sandbox/`: digest-pinned Dockerfile (shell binaries removed, non-root, no dev group, entrypoint = `mcp-serve`) and README (internal network by default, live fixtures and PR push as explicit sidecar escapes). Tests 412 → 641 (621 unit + 20 `db`); `targets/` still only `__init__.py`.

**Formalisations recorded in the plan (P3-D1 … P3-D10):** stdlib MCP transport; `open_pr` prepares, never pushes; goldens run the generic pipeline and the custom-parser loader stays deferred (P2-D8) with an ADR as its route; golden file format; completeness enforced by lint and by collection; PR-surface rule; the normalise and positional AST rules; two fixture-recording modes; the workload checker covers what exists today.

**Learned.** On this interpreter uv's editable `.pth` is skipped as "hidden", so the package is importable only from the repository root: scripts run as `python -m scripts.<name>` and pytester subprocesses get `PYTHONPATH` set — recorded in the memory quirks. In-process `pytest.main` needs `--import-mode=importlib` or two targets' `tests/test_golden.py` collide. `httpx`'s `MockTransport` exposes no peer address, so the CLI's `--live` under the socket block fails at name resolution with the ADR-027 `RuntimeError` — the negative test asserts exactly that. `make check | tail` hides a red exit; use a log file.

**Open / carried.** Custom `parser.py` execution (05 §5); layer-1 NetworkPolicy verification, restricted-PSS script, rollback drill (Phase 5); `mapping.ignore_fields`, delivery-day offset, F13, V-12 … V-14, F09/F12 as before. `CODEOWNERS` still carries the placeholder handle (F09).

**Next prompt** (03 Phase 4 starter, verbatim):

```text
Read CLAUDE.md, docs/01-data-scope.md §3, §5, §7, §9, §10, docs/04-contracts.md, docs/05-constraint-matrix.md and docs/03-roadmap.md Phase 4. For T1, T2, T3 in that order: scaffold with energyctl, verify the live endpoint once, record a fixture, write goldens with values you checked by hand against the fixture, and open a PR touching only targets/<id>/. Then add E1 strictly through the contributor workflow as the adapter-addition demo. Do not add any 01 §4 candidate. Record findings in docs/06-source-verification.md. Stop when all four pass contract tests offline.
```

---

## 2026-09-20 — Phase 2 close: S3 Bronze backend (ADR-032 Option B)

**Done** (`docs/plans/phase-2.md` appendix Task 2.10, 4 commits, `make check` green at each): `energy_platform/fetch/objectstore.py` — a minimal S3 client over `httpx` inside the single egress package: SigV4 as a pure function (`sign_v4`, proven against the AWS documentation vector: canonical-request hash `7344ae5b…6972`, signature `f0e8bdb8…db41`), `PUT`/`GET`/`HEAD`/`LIST` (ListObjectsV2 following `NextContinuationToken`)/`DELETE` (refused unless `allow_delete=True`, reserved for the ADR-021 tiering job), path-style addressing, `x-amz-content-sha256` always the payload hash, `Content-MD5` on every `PUT`, `x-amz-object-lock-mode` / `…-retain-until-date` from a configured `Retention` (V-6), endpoint host checked against a configured allowlist before any request (`https` unless `allow_insecure`; no userinfo, path, query), credentials from the environment through the `secretRef` resolver (`<NAME>_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY`, optional `_SESSION_TOKEN`), retries on connection errors and 5xx only via the existing `RetryPolicy`, secret hidden from `repr` and errors. `energy_platform/bronze/s3.py` — `S3BlobStore` (ADR-002 key `bronze/blobs/<sha[:2]>/<sha>`; `HEAD` then `PUT`, so a second write of the same content sends no `PUT`) and `S3CaptureLog` (`captures/<t>/<Y>/<M>/<D>/<stamp>_<n>.json`; `get` derives the key from the `capture_id`, `entries_for` lists the instant prefix, `list`/`latest` decide the window from keys and fetch only the matching entries; `tier` round-trips untouched); a second `S3BlobStore` is the `cold=` store of the unchanged `Bronze` facade. Tests (all offline, socket block on): `tests/fetch/fake_s3.py` — an in-memory gateway behind `fetch.offline.mock_transport` that checks path style, the content hash, the `Authorization` shape and the signed-header set, records requests, answers MinIO-shaped XML with a server-side page cap; `tests/fetch/test_objectstore.py` (21) and `tests/bronze/test_s3.py` (9). Tests 382 → 412 (392 unit + 20 `db`). ADR-027 §3 amended by one sentence naming `fetch/objectstore.py`; ADR-032 marked implemented; `04` §6 rows; roadmap Phase 2 S3 box un-struck and ticked. No new dependency (`make deps-allowlist` unchanged).

**Formalisations recorded in the plan (P2-D15 … P2-D20):** verbs and the delete flag; endpoint policy is its own allowlist, not the source host registry nor the private-range rejection (the store is a private destination that ADR-026 layer 1 allows explicitly); credentials by `secretRef` names; `Content-MD5` + object-lock headers on `PUT` and `HEAD`-before-`PUT`; key-derived lookups in the capture log; the fake gateway plus the AWS known-answer vector as the offline proof.

**Learned.** The ADR-027 socket block surfaces as a bare `RuntimeError` from inside `httpx`'s connection pool (not a `TransportError`), so a real transport in a unit test fails before the retry loop can swallow it — the test asserts exactly that. S3 requires `Content-MD5` when object-lock headers are present; sending it always costs nothing. httpx drops the default port from the `Host` it sends, so the signer sets `host` explicitly from the URL it signs and the client sends the signed header set verbatim.

**Open / carried.** First live use of the backend is Phase 5 `local-up` (MinIO ×2) and the demo stores (Hetzner/OCI, V-12/V-13). The CLI still builds Bronze on a directory (`--bronze-dir`); wiring the S3 backend from chart values/env is a Phase 5 task with the `Secret` mapping. Everything else as in the Phase 2 entry below (`mapping.ignore_fields`, delivery-day offset, `parser.py` loader in Phase 3, F13, V-12 … V-14, F09/F12).

**Next prompt** (03 Phase 3 starter, verbatim):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md (ADR-005 to ADR-008), docs/04-contracts.md and
docs/03-roadmap.md Phase 3. Write docs/05-constraint-matrix.md first. Then implement scaffolder,
MCP server and CI gates so that every matrix row has a mechanical gate and a negative test. Stop
when all negative tests are rejected by their mapped gate.
```

---

## 2026-09-20 — Phase 2: platform core library (fetch → bronze → parse → mapping → store → runtime → CLI)

**Done** (`docs/plans/phase-2.md`, 9 commits, `make check` green at each; `make db-test` and `make demo` green on PostgreSQL 18): ADR-030 (D-2 engine: plain PostgreSQL ≥ 16, no extension), ADR-031 (D-4 gap-detector defaults), ADR-032 **PROPOSED** (S3 client for the Bronze backend — the author decides; nothing implemented). Runtime deps `httpx`, `lxml`, `openpyxl`, `psycopg`, `alembic`, `sqlalchemy`, `typer` locked and allowlisted with their closure (ADR-019), stubs `lxml-stubs`, `types-openpyxl` (ADR-029). `energy_platform/fetch/` — ADR-026 layer 2 (manifest **and** registry host check, scheme, port, IP-literal refusal, private/metadata/CGNAT rejection on resolution, peer re-check, redirects followed by hand ≤ 3 hops each validated, 4 attempts with capped jittered backoff on connection errors/5xx only, `If-None-Match`/`If-Modified-Since` with 304, token-bucket rate limit, secret redaction, offline fixture/mock transports so nothing else imports `httpx`). `bronze/` — blob then entry, idempotent per `(target_id, scheduled_for)`, attempts from the prefix, `content_changed`, hot→cold read with the content address verified, memory and filesystem backends, fixtures = Bronze objects. `parse/` — decoders (openpyxl floats as `Decimal(repr)`, lxml with entities/network off, SOAP `Fault`, json, csv, html-table with a minimal selector subset) and generic record parsers built from the manifest (P2-D5). `mapping/` — period index / offset-aware timestamp → UTC interval, decimals under the declared separator, NULL never zero, sign rules, quarantine causes, `unknown_field`, `negative_value`, `partition_status` (92/96/100 from the calendar), `reconciliation_mismatch` (01 §3 rule 2, both directions). `store/` — migrations `0001_ledger`, `0002_silver` (tstzrange + generated `delivery_start_utc`, jsonb dimensions, `UNIQUE … NULLS NOT DISTINCT` version identity, `observations_current` view with ADR-023 §3 ordering), each with a downgrade; `Store` protocol with fenced `claim`/`renew`/`commit` (`SELECT … FOR UPDATE` under the fence; stale holder = `lost_lease`, zero rows), replay queue, derivations; `MemoryStore` and `PostgresStore` with one parametrised suite (six ADR-023 proofs, fencing, ledger). `runtime/` — `capture` (ledger last, best-effort), `reconcile`, fenced `process` (quarantine keeps Bronze), `replay` by range/derivation (never fetches), `backfill`, gap detector per ADR-031 with a five-field cron evaluator (92/100 instants on DST days) and calendar `history.max_age`; the eight ADR-024 §6 crash rows as tests. `energyctl validate | capture (--fixture | --live) | process | replay | backfill | gaps | migrate | demo`; `capture` needs no database. `examples/fixtures/` (synthetic Bronze objects for T1, T2, T3; `make fixtures`). `make db-test` (ephemeral `initdb`/`pg_ctl` on a Unix socket via `scripts/with_postgres.sh`, upgrade→downgrade→upgrade round trip) and `make demo`, both CI jobs. Tests 187 → 382 (362 unit + 20 `db`), all offline.

**Formalisations recorded in the plan (P2-D1 … P2-D14, plus the "Deviations" section):** one `Store` protocol (fencing couples Silver and ledger); generic parsers keyed on the mapping's time/version fields; `unknown_field` is a warning because the manifest cannot declare display-only columns (04 §5 open question); delivery day derived from `scheduled_for` (04 §5 open question, D-5); `history.max_age: none` = no history; pending replay = attempt with `outcome IS NULL`; peer check skipped only for declared-offline transports; ČEPS example maps `@value1`/`@value2`.

**Learned.** The `energyctl` console script cannot import the editable package on this path (same quirk as Phase 1): Make targets run `python -m energy_platform.cli`. psycopg goes through libpq's own sockets, so the ADR-027 Python socket block does not interfere with `db` tests and no network is involved. ruff S311 flags `random.Random(...)` even for jitter: tests use `SystemRandom`, the library takes an injected `random.Random`. `urlunsplit` collapses the `///` of a socket DSN. bandit S608 is satisfied by `psycopg.sql` composition. Ruff's per-file `TID251` exception was **not** widened: fetch tests get transports from `energy_platform.fetch.offline`.

**Open / carried.** ADR-032 (S3 client) was ACCEPTED as Option B (SigV4 over `httpx` inside `fetch/`, no new dependency) at the end of the session; the S3 backend is the first task of the next session, then Phase 3 begins. Until then Bronze has memory and filesystem backends only — the roadmap box stays struck through with the pointer. Two 04 §5 questions need ADRs before Phase 4: `mapping.ignore_fields` (T2 `Time interval` warns on every run) and a delivery-day offset for "hourly for D-1..D-3" (with D-5). Custom `parser.py` loading is Phase 3 (P2-D8; dynamic import is banned platform-wide, the loader needs its own recorded exception). F13 (ČEPS `interval_label`), V-12..V-14, F09/F12 unchanged.

**Next prompt** (03 Phase 3 starter, verbatim):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md (ADR-005 to ADR-008), docs/04-contracts.md and
docs/03-roadmap.md Phase 3. Write docs/05-constraint-matrix.md first. Then implement scaffolder,
MCP server and CI gates so that every matrix row has a mechanical gate and a negative test. Stop
when all negative tests are rejected by their mapped gate.
```

---

## 2026-09-20 — Phase 1: contracts (package, schema, six example manifests)

**Done** (`docs/plans/phase-1.md`, 11 commits, `make check` green at each): ADR-029 (typing stubs for allowlisted packages are dev deps); runtime deps `pydantic`, `pyyaml`, `tzdata` locked and allowlisted (ADR-019); `energy_platform/contracts/` — `intervals.py` (DST-safe local-day tiling, 92/96/100 by construction; index → interval; timestamp + `interval_label`), `decimals.py` (explicit dot/comma, quarantine on ambiguity, sign inversion), `registry.py` (`ote.idm_continuous`, `ote.dam`, `ceps.load` with identity keys, fixed/constrained dimensions, metric unit/currency/sign/NULL-meaning/owner transport), `hosts.py` (`www.ote-cr.cz`, `www.ceps.cz`), `observation.py` (`EnergyObservation` validated against the registry; `observation_identity`, `version_identity`, `derivation_id`), `parser.py` (`DecodedDocument` shapes, `SourceRecord`, `Parser`), `manifest.py` (model, YAML-subset loader, structural + admission validation with `ADMISSION_REQUIRED` gaps); `schemas/manifest.v1.json` exported by `make schema` with a staleness test; `examples/manifests/` — T1, T2, T3 admitted, html-table admitted, rest-json and ENTSO-E rest-xml return `ADMISSION_REQUIRED`; `docs/04-contracts.md`. 151 new tests (property tests with Hypothesis).

**Formalisations recorded in the plan (P1-D1 … P1-D7):** Silver rows are metric-long (identity = 01 §6.3 key ⊕ `metric` ⊕ `source_version`); the ceps.load `version` dimension is bound to `source_version`; `fetch` is keyed by modality; example manifests live in `examples/`, not `targets/`; ENTSO-E is the rest-xml example (roadmap wording fixed); `decimal_separator` is explicit; stubs via ADR-029. None adds a field 01 does not name.

**Learned.** ruff 0.16 formats Python blocks inside Markdown (`make check` covers docs; pseudo-code blocks are tagged `text`). On this path the editable install is not visible to `python scripts/x.py` but is to `python -m scripts.x`; the `schema` Make target uses `-m`. Task 1.2 (04-contracts) was written after the code modules so it documents the shipped field names rather than a draft.

**Open / carried.** F13 (ČEPS `interval_label: start` `[UNVERIFIED]`) stays a Phase 4 task; the T3 example carries the note. The transport check in `validate_manifest` accepts a non-owning transport delivering an owned metric (01 §3 rule 2: stored and reconciled) — the reconciliation itself is Phase 2. `ValidationResult` is what Phase 3 `energyctl validate` prints. No new open decision.

**Next prompt** (03 Phase 2 starter, verbatim):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md, docs/adr/ADR-003-rev-orchestration-without-crds.md,
ADR-016, ADR-023, ADR-024, ADR-026 (fetch layer), docs/04-contracts.md and docs/03-roadmap.md Phase 2.
Plan into docs/plans/phase-2.md. Implement the library in the order fetch → bronze → parse → mapping →
silver → ledger → replay/gaps → CLI, committing per module with tests. Every migration has a downgrade
script. `make demo` must run offline. Stop when it does.
```

The D-2 ADR (Postgres engine: plain vs TimescaleDB) is written before the Phase 2 schema is created.

---

## 2026-09-19 — ADR-028: demo environment (docs only, no platform code)

**Why.** Roadmap Phase 5 had the tenant profile running for real on the e-INFRA Rancher cluster. e-INFRA CZ terms cover research and education; this is a commercial deliverable, so a scheduled workload there is out of policy. One-off probes (V-4 … V-10) stay.

**Decided** (`docs/adr/ADR-028-demo-environment.md`, ACCEPTED): three environment words — *reference* (MetaCentrum, probes only, no release), *demo* (author-paid, handed to the evaluator live), *production* (ČEZ). Demo = Hetzner Cloud two-node k3s built by the `own-cluster` Terraform through a new `hcloud` root sharing modules with the `openstack` root, deployed with `tenant` values into a namespace-scoped Role so one cluster proves both profiles; Bronze store A on Hetzner Object Storage, store B on OCI Object Storage Frankfurt (S3-compatible endpoint, retention rule) — two providers, two countries, which is what A-3 means by independent. Residency declared `DE` on the demo. Budget alerts before the first apply; apply/destroy/bucket deletion stay Level 3 (author). Rejected: stay on MetaCentrum, OCI-only (free ARM tier halved 2026-06-15, capacity, multi-arch), Hetzner-only (one operator), OKE, a `demo` profile.

**Reconciled.** `02` ADR-001 paragraph and `tenant` bullet, §4.2 D-1/D-3, §4.3 V-11 … V-14; `00` §2.1 row, A-9 note, §4 V-12 … V-14, §6 checklist; ADR-001 amendment header; `03` Phase 5 (demo cluster, `hcloud` root, A → B replication, cost guard, V-12 … V-14 gate) and Phase 8 (live-demo block).

**Open, author-run before Phase 5 Terraform work:** V-12 (does Hetzner Object Storage support Object Lock?), V-13 (OCI retention + `rclone` A → B), V-14 (k3s structured auth with GitHub OIDC). Accounts exist: Hetzner project, OCI pay-as-you-go. Credentials outside the repository.

**Next.** Phase 1 (contracts), unchanged.

---

## 2026-09-19 — Review 1: Codex pre-coding verdict answered (docs + gates, no platform code)

**Input.** `codex-review/` (14 findings, 9 P1) against `7d872ea`. Verdict accepted: design checkpoint, not a submission; the executable gates were thinner than the documents claimed. Response per finding: `docs/reviews/2026-09-19-codex-review-response.md`; plan: `docs/plans/review-1.md`.

**Decided** (`docs/adr/`, all ACCEPTED): ADR-022 source admission vs adapter addition (two routes; escalation is a pass in Phase 7); ADR-023 derivation identity (version key gains `derivation_id`; `contract_version` ≠ implementation; current view by capture ordering basis then derivation); ADR-024 capture recovery (Bronze capture-log entry is the durable boundary, `reconcile` rebuilds the ledger, `run_attempts` + fencing at commit, backfill ≠ replay, `history.max_age`); ADR-025 upgrade hooks (`smoke` = `post-install,post-upgrade,test`; `migrate` = `post-install,pre-upgrade`; probe joins the chain); ADR-026 egress boundary (NetworkPolicy = coarse layer with private/metadata `except`; per-host, resolution and redirect checks in `fetch` against a CODEOWNERS host registry; V-11 added); ADR-027 target capability boundary (positive file and import allowlists for targets, extended banned-API list, unit-test socket block).

**Gates now real** (`make check` = lint + lock-check + type + test; 36 tests): `targets/**/tests` collected by default (pytester negative test); `scripts/check_target_surface.py` in `make lint` with 11 negative tests; ruff TID251 covers `http.client`, `socket`, `subprocess`, `importlib`, … outside `fetch/`; root `conftest.py` disables sockets unless `live`; secret-scan exempts the matched value, not the line (7 tests); `uv lock --check` in `check` and CI; hatchling, uv installer and `actions/checkout` pinned; pre-commit runs the same three gates as CI. Re-ran the reviewer's probes: the `http.client` parser fails lint, the planted failing target test fails the default run, a stale lock fails `lock-check`, the "token + # example" line is reported.

**Learned.** A gate that is only a ban list is bypassed by the standard library; a positive allowlist on the smallest surface (targets) plus a runtime block is what actually holds. `helm test` hooks are not part of `--atomic`. Standard `NetworkPolicy` has no hostnames. `--frozen` is not `--locked`. Three findings were premises, not code: "cannot ask the evaluator" was reworded to a choice.

**Blocked on the author.** F09: a Git remote and a real handle for `CODEOWNERS`, then apply `docs/branch-protection.md`. F12: the original `message-board/evidence/` ledger for the energy task was not found on this machine (the two message-board directories on disk belong to other projects); either supply it or let Phase 4 regenerate `docs/evidence/`.

**Not done, by design.** No Phase 1 code (one phase per session, 03 §0). `docs/01-data-scope.md` untouched; F13 (ČEPS interval labelling) is a Phase 4 verification task. `codex-review/` committed verbatim as evidence.

**Next prompt** (03 Phase 1 starter, as amended):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md (§2 ADR-005, ADR-011, ADR-013; §4.1), docs/adr/ADR-017 … ADR-020 and ADR-022, ADR-023, ADR-026, ADR-027, docs/01-data-scope.md, docs/reviews/2026-09-19-codex-review-response.md, and docs/03-roadmap.md Phase 1. B-1, B-2, B-3, B-6 are resolved; implement them as amended. Author docs/04-contracts.md and implement the contracts package (observation, registry, hosts, manifest, parser protocol) with the property and negative tests. Stop when the six example manifests validate and the DST tests pass.
```

---

## 2026-09-19 — Reconciliation of 02/03 with 01 v1.0 (docs only, before the pre-coding review)

02 and 03 had been written against 01 v0.1's wide catalogue. Corrected, each with a dated note: 02 §1.1 scope wording (intraday market results as the core; modality matrix = framework test suite, not live targets); ADR-002 capture-log field names follow 01 §6.1; ADR-005/ADR-013 fetch spec gains the declarative discovery step T2 needs and a `contract` block; ADR-011 points at 01 §6–§9 as source; ADR-012 freshness per 01 §5, "per tier" dropped; §3 step 4 and V-1 reworded; D-5 default = 01 §5 intervals; D-11 default → out. 03 Phase 1 example manifests (three real, two shape-only) and 04-contracts source; Phase 4 reduced to T1, T2, T3, E1 + the restricted stub, candidates explicitly not built, fixtures per 01 §7/§9, one-week polling campaign; Phase 7 unseen-source wording. CLAUDE.md/AGENTS.md/README scope line.

**Still open for the review:** `01-data-scope.md` cites `message-board/evidence/` (S01–S17) which is not in this repository — either add the evidence files or reword the citations before submission. 01 itself was not edited.

---

## 2026-09-19 — Phase 0: repository bootstrap — DONE

**Gate:** `make check` green on the empty package (ruff incl. egress ban, mypy --strict, import-linter 2 contracts kept, 1 placeholder test). Ten commits, one per task plus one fix.

**Delivered.** `pyproject.toml` (Python 3.12, uv, hash-pinned `uv.lock`, ruff DTZ/S110/S113/TID251 banned-api for httpx/requests/urllib/urllib3/aiohttp outside `energy_platform/fetch/`, mypy strict, import-linter layers); empty `energy_platform/` + `contracts/`, `targets/`, placeholder test; `Makefile` with `check/lint/type/test`, `deps-allowlist`, `secret-scan`, `helm-lint`, `terraform-validate`, `ci-bootstrap`, and honest stubs (`local-up`, `local-down`, `smoke-test`, `demo`, `new-target` exit non-zero with the phase that implements them); `deps-allowlist.txt` (31 packages, transitive included) + `scripts/check_deps_allowlist.py`; `scripts/secret_scan.py`; `.github/workflows/ci.yml` (7 jobs, every step is `make <target>`); `.pre-commit-config.yaml`; `CLAUDE.md` = `AGENTS.md`; `CODEOWNERS`; PR template; `docs/branch-protection.md`; `docs/threat-model.md` stub (10 headings); `README.md` stub; `.gitignore`.

**Verified.** Negative tests run by hand: a lock with `totally-hallucinated-pkg` fails `deps-allowlist` (exit 1, names it); a file with an AWS key-id pattern fails `secret-scan`; `helm-lint`/`terraform-validate` skip with exit 0 when their inputs are absent and fail with exit 1 when present without the tool (a first version continued past the skip; fixed in `ee8148c`).

**Learned.** ruff's S-rules caught the bootstrap scripts themselves (partial executable path, subprocess); kept the rules, fixed the scripts. Multi-line Make recipes run each line in a fresh shell, so a skip must be a single block.

**Not done / flagged.** `CODEOWNERS` has a placeholder handle; replace before branch protection. `scripts/check_restricted_pss.py` referenced by `helm-lint` is a Phase 5 deliverable (the target cannot reach it before the chart exists). No remote configured. `pre-commit` is in the dev group but not installed into `.git/hooks` (`uv run pre-commit install` when wanted). `energyctl` entry point deferred to Phase 2. D-2 engine choice still needs its ADR before the Phase 2 schema.

**Next prompt** (03 Phase 1 starter, verbatim):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md (§2 ADR-005, ADR-011, ADR-013; §4.1), docs/adr/ADR-017 … ADR-020, docs/01-data-scope.md, and docs/03-roadmap.md Phase 1. B-1, B-2, B-3, B-6 are resolved; implement them. Author docs/04-contracts.md and implement the contracts package with the property tests. Stop when the five example manifests validate and the DST tests pass.
```

---

## 2026-09-19 — Decisions session (no platform code)

**Verified** (`00-assumptions.md` §5; access: e-INFRA Rancher kubeconfig, MetaCentrum Cloud Brno1 application credential, CESNET S3, e-INFRA LLM; all credentials kept outside the repository):

| V | Verdict | One line |
|---|---|---|
| V-4 | CONFIRMED | Tenant only: no CRDs; CronJobs/NetworkPolicies allowed; `restricted` Pod Security enforced; ingressclass list Forbidden; Argo CRDs present but CronWorkflow create denied; CNPG, cert-manager, prometheus-operator creatable in-namespace; no External Secrets; quota 6/10 CPU, 5/9 GiB |
| V-5 | CONFIRMED | No Magnum in Brno1 catalog; quota 20 vCPU / 10 instances / 50 GB / 1 network / 1 floating IP; Ubuntu jammy+noble images |
| V-6 | CONFIRMED | S3 (Ceph RGW) versioning + object lock + lifecycle verified on store A; Swift on a separate Brno endpoint verified as store B; storage-class probe: only STANDARD exists, lifecycle accepts unknown classes silently → ADR-021 (tiering job) |
| V-7 | CONFIRMED | OpenAI-compatible endpoint, 34 models |
| V-8 | CONFIRMED | Federated (Shibboleth/Perun) identity; kubeconfig is an opaque Rancher token with 1-year TTL. Second pass: Rancher mints ≤ 5-min cluster-scoped tokens from an existing token (no tenant-creatable CI principal); SA TokenRequest JWTs are rejected by the Rancher proxy → two-token CI pattern (ADR-015) |
| V-9 | CONFIRMED | No proxy; OTE, ČEPS, ENTSO-E reachable from a pod |
| V-10 | CONFIRMED | No managed Postgres; CNPG operator pre-installed |

Register changes: A-5 cost-if-false updated; A-13 (GitHub Actions) and A-14 (`restricted` PSS) added.

**Decided** (`docs/adr/`, all ACCEPTED): ADR-001-amend (three profiles; MetaCentrum = reference environment), ADR-003-rev (CronJob + run ledger, no CRDs), ADR-014 (tooling), ADR-015 (GitHub Actions as thin wrapper over Make; A-13), ADR-016 (release and rollback), ADR-017 (manifest YAML/JSON Schema/directory convention/`secretRef`), ADR-018 (`tstzrange`, append-only versions, both timestamps), ADR-019 (five parsers, dependency allowlist), ADR-020 (Bronze fixtures, YAML goldens, Hypothesis, nightly smoke), ADR-021 (Bronze cold tier as a platform `rclone` tiering job with deploy-time probe; resolves D-8; filed after a follow-up storage-class probe the same day). `02` reconciled with superseded text kept; `03` Phases 0–3, 5, 8 and appendices reconciled; `00` §6 all ticked. No phase checkbox ticked.

**Contradictions found:** none against `00` §3. Two nuances recorded: (1) Argo is installed on the reference cluster yet unusable by a tenant, which strengthens ADR-003 rev.; (2) kube access is not a short-lived OIDC token, so the "no static kubeconfig secrets in CI" line in A-5 is replaced by the two-token pattern in ADR-015 (verified: Rancher mints 5-min cluster-scoped tokens; SA tokens do not pass the proxy).

**Still open:** V-1, V-2, V-3 (Phase 4 / documentation tasks); D-1, D-3, D-4, D-5, D-9 … D-12 (deferred by design); D-2 engine choice (ADR before Phase 2 schema). No `CLAUDE.md` exists yet (Phase 0 deliverable); the repository was `git init`-ed this session with docs only.

**Next prompt** (03 Appendix A, verbatim):

```text
You are working in the energy-platform repository. Read, in order: CLAUDE.md,
docs/00-assumptions.md, docs/01-data-scope.md, docs/02-architecture-decisions.md,
docs/adr/ (all ACCEPTED), docs/progress.md, docs/03-roadmap.md.

Rules that override anything else you infer:
- Locked decisions in 02 §2 and ACCEPTED ADRs in docs/adr/ are frozen. Open items in
  02 §4 are resolved only by writing a one-paragraph ADR in docs/adr/ before
  implementing the default. B-1…B-6 are already resolved; do not rewrite them.
- The core chart is a tenant: no CRDs, restricted Pod Security, requests/limits on
  every workload. Orchestration is CronJob + run ledger (ADR-003 rev.), not Argo.
- Harness before code: no target under targets/ before Phase 3 is complete.
- Targets contribute manifest + optional parser + fixtures + golden tests, nothing else.
  Fetch and normalise are platform code.
- No new dependency without an ADR and an allowlist entry.
- Plan into docs/plans/phase-N.md before coding. One task, one commit, `make check` green.
- Update docs/03-roadmap.md checkboxes and docs/progress.md at the end of the session.

Begin Phase 0.
```
