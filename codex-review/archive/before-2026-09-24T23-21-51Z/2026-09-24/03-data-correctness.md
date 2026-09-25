# Data engineering and energy-domain correctness

Reviewed 2026-09-24 at commit `1701ac77175113d744abaad0514489711ed2b1d4`. Source and infrastructure were not changed. This report is a read-only audit; the only writes are review artifacts. The older review is preserved.

## Verdict

The repository has progressed from a design to a working ingestion platform. Durable raw capture, typed observations, database migrations, lease fencing, correction polling, replay, native-resolution mapping, source-specific fixtures, and restore tooling are implemented. Independent inspection of the native fixtures supports the ordinary numeric and DST mapping behavior.

However, **the current implementation does not yet satisfy dependable correction handling or authoritative current-data selection**. Eight independently reproduced findings below identify six P1 defects and two P2 defects. Several preserve the original bytes while silently leaving the wrong canonical value current. A successful backup drill also does not establish that restored data is semantically safe: the documented deletion of known-wrong T2 data is not replay-safe.

Severity: **P1** means incorrect canonical data, loss of a captured observation's discoverable provenance, or recovery that can restore known-invalid current data; **P2** means a bounded but material recovery or monitoring failure.

## Verification performed

The runnable artifacts are deliberately named `.py.txt` so they do not become part of repository lint/test discovery. Run from the repository root with the existing environment:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python codex-review/2026-09-24/evidence/data-correctness-probes.py.txt
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python codex-review/2026-09-24/evidence/independent-fixture-check.py.txt
```

- [Data counterexample script](evidence/data-correctness-probes.py.txt) and [exact output](evidence/data-correctness-probes.log): eight groups, all reproduced using the real runtime and memory stores. All mutations are in memory; the concurrent-capture probe uses two threads and a barrier to force a valid overlapping read-before-write schedule.
- The coordinating reviewer independently reran the memory probes and reproduced **DC-01, DC-02, DC-03, DC-04, DC-05 and DC-08 using an ephemeral PostgreSQL 18.4 instance**, not the live database: [PostgreSQL script](evidence/postgres-counterexamples.py.txt), [output](evidence/postgres-counterexamples.log). DC-06 and DC-07 remain memory-runtime reproductions supported by the inspected production code paths.
- [Independent fixture check](evidence/independent-fixture-check.py.txt) and [output](evidence/independent-fixture-check.log): **42 positive fixtures across all seven targets**, **215 sampled golden values and UTC instants**, and declared row counts totaling **45,493 rows** all matched. This script imports **zero `energy_platform` modules** and does not consume the platform's manifest mapping, parser, mapping engine, interval helper or golden runner. It reads native XML or XLSX, parses values with `Decimal`, and derives UTC interval starts independently with `zoneinfo` and the source indices/offsets.
- The independent check covers ordinary days, spring/autumn DST, hourly native observations, negative and zero prices, NULL values, and settlement versions 0/1/2. Quarantine fixtures were deliberately excluded from this positive arithmetic cross-check; existing platform tests cover them.
- Broad checks and live/GitHub evidence are recorded by the coordinating reviewer elsewhere in this review. Passing those checks does not invalidate the counterexamples below; those cases are absent from, or insufficiently asserted by, the current tests.

## Findings

### DC-01 — P1: a correction captured during a database outage is not reconciled into an existing run

**Evidence:** `energy_platform/runtime/capture.py:98` and `:135`–`:148`; `energy_platform/runtime/reconcile.py:18`–`:33`; `energy_platform/store/postgres.py:203`–`:215`; memory equivalent `energy_platform/store/memory.py:91`–`:96`.

The capture path correctly persists Bronze before acknowledging the ledger and tolerates `StoreUnavailable`. But recovery calls `ensure_run`, whose conflict update advances a run only when it is **not processed and has no capture ID**. It cannot replace an existing run's older capture with a newer durable correction. Reconciliation reads the newest Bronze entry, calls that no-op update, and reports nothing changed. The normal process selector consequently sees no pending work.

**Reproduction:** capture and process price `170.13`; change the source to `171.99`; inject a ledger outage during forced capture; recover the store and run full reconciliation and processing. Bronze contains attempt 2 with `content_changed=true`, but the ledger still refers to attempt 1. Output: `reconciled=0`, `processed_after_recovery=0`, current price `170.13`. This also reproduced on PostgreSQL.

**Impact:** a successful durable correction can be ignored indefinitely. A later unchanged recapture does not repair the handoff because `_ack` calls `mark_recaptured` only when that recapture's content changed. The same problem affects runs already carrying a capture ID even if their state is still `captured` or `failed`. The default 48-hour reconciliation filter uses `scheduled_for`, so recovering corrections to older delivery days also needs explicit consideration.

**Recommendation:** reconcile durable capture generations, not just the existence of a run. Record which capture generation has been processed and atomically queue any newer eligible generation; make this work after a lost acknowledgment and across the full configured correction window. Add a crash-matrix case with an already-processed run and a new correction, including a subsequent unchanged poll.

### DC-02 — P1: recapture does not invalidate an in-flight process claim

**Evidence:** `energy_platform/store/postgres.py:262`–`:270`, `:335`–`:338`, `:394`–`:397`; `energy_platform/runtime/process.py:75`–`:80`; memory equivalent `energy_platform/store/memory.py:119`–`:122`.

`mark_recaptured` changes the run's capture ID and state without advancing its fence or binding the old claim's commit to the capture it read. An existing worker therefore retains a valid fence for its older capture. Its commit writes the old data and changes the run back to `processed`, even though the run now points at the newer correction.

**Reproduction:** capture A; claim it with worker 1; force capture B before worker 1 commits; process worker 1's old claim; run normal processing again. Output: worker 1 `ok`, old fence and current fence both `1`, run `processed`, pending `0`, current price still A. Reproduced on PostgreSQL as well.

**Impact:** ordinary overlap between correction polling and processing can silently skip B. Fencing protects against a replacement *claimer* but currently does not protect against this other mutation of the claimed work.

**Recommendation:** make correction registration and process commit agree on a work generation. A commit for A must either lose its claim when B arrives or leave B pending after A's transaction completes. Test the interleaving on PostgreSQL, not only with sequential happy-path recaptures.

### DC-03 — P1: the canonical current view disregards T1/T2 metric ownership

**Contract:** `docs/01-data-scope.md:101` specifies SOAP T1 as the system of record for `price_vwap` and `volume_total`; XLSX copies are retained for reconciliation. The registry encodes this in `energy_platform/contracts/registry.py:35` and the corresponding IDM metric entries.

**Evidence:** `energy_platform/silver/migrations/versions/0002_silver.py:79`–`:93`; `energy_platform/store/ordering.py:23`–`:27`; `energy_platform/store/postgres.py:520`–`:543`; memory equivalent `energy_platform/store/memory.py:301`–`:337`. Current selection partitions without transport and ranks by timestamp/derivation, without consulting `owner_transport`. The optional transport filter is applied **after** selecting that global winner. `tests/store/test_store.py:138`–`:171`, despite its ownership-proof name, explicitly accepts selection by fetched time rather than transport and uses equal values/timestamps that do not prove the ownership rule.

**Reproduction:** publish SOAP price `999.00`, then one minute later process XLSX with price `170.13`. The reconciliation warning is correctly recorded, but canonical current becomes `170.13` from XLSX. Querying current `price_vwap` with `transport="soap"` returns **zero rows**, although the SOAP observation remains stored. Reproduced on PostgreSQL.

**Impact:** consumers of the canonical view receive the reconciliation copy as authoritative; filtering for the owner can make authoritative data disappear. Subsequent comparisons can also lack the other transport's current value because `_other_transport_rows` reads this same global view (`runtime/process.py:180`–`:199`). This is a semantic violation, not merely a dashboard naming issue.

**Recommendation:** retain an independently selectable latest value per transport, and apply registry ownership when producing the canonical view. Reconciliation should compare transport-specific latest values. Add tests with differing values, unequal fetch times, both arrival orders, replays, and corrections.

### DC-04 — P1: an A → B → A provider correction leaves B current

**Evidence:** `energy_platform/contracts/observation.py:150`–`:152`; `energy_platform/silver/migrations/versions/0002_silver.py:55`–`:60` and `:87`–`:93`; insertion in `energy_platform/store/postgres.py:59`–`:65`; memory equivalent `energy_platform/store/memory.py:195`–`:205`.

Version identity deduplicates observation identity + payload hash + derivation across every capture. The retained row carries the first capture's `fetched_at`. A later return to a previously observed payload is treated as an exact retry, even when it follows a different provider correction. No relationship updates the version's latest occurrence for current selection.

**Reproduction:** capture/process A (`170.13`), B (`171.99`), then the byte-identical A again. All three captures are recorded, and the third is `content_changed=true`. Process results are `ok/192`, `ok/192`, then `noop/0`. Current stays `171.99`, contrary to the most recent provider payload. Reproduced on PostgreSQL.

**Impact:** a valid provider reversion cannot become current using the same derivation. This is distinct from the required rule that replaying an *older* capture must not outrank a newer capture; here the third capture is genuinely newer.

**Recommendation:** distinguish exact reprocessing of one capture from a new occurrence of a previously seen payload. Keep capture-to-derivation occurrence lineage or another append-only occurrence representation that permits current selection by the newest eligible capture without duplicating exact retries. Update ADR-023's identity/ordering contract together with the implementation and test A→B→A plus replay of each capture.

### DC-05 — P2: a claimed replay is abandoned permanently if its worker dies

**Evidence:** `energy_platform/store/protocol.py:72`–`:73`; `energy_platform/store/postgres.py:446`–`:454` and the replay claim update at `:289`–`:305`; `energy_platform/runtime/process.py:54`–`:62`.

A queued replay is pending only while `lease_owner IS NULL`. Claiming it sets its lease owner, while the parent run remains `processed`. After a crash and lease expiry, `pending_runs` selects neither the processed run nor the owned unfinished replay. No timeout/reclaim condition makes it visible again.

**Reproduction:** process a run, enqueue a replay, claim it, advance the clock beyond lease expiry without committing, then call `process`. Output: `run_state=processed`, `lease_expired=true`, `pending_runs=0`, `process_reports=0`, and an unfinished replay still owned by the dead worker. Reproduced on PostgreSQL.

**Impact:** a planned repair can stop permanently after one worker failure despite the platform's automatic recovery model. An operator can enqueue new work manually, but that is outside the promised lease-driven recovery.

**Recommendation:** include unfinished attempts with expired leases in reclaimable work, and define a consistent transition for the prior attempt's outcome. Add replay-specific crash/reclaim/fencing tests; the existing initial-process lease test does not cover a replay on an already-processed run.

### DC-06 — P1: concurrent capture writers can overwrite the same capture-log entry

**Evidence:** `energy_platform/bronze/bronze.py:74`–`:77` and `:95`–`:115`; `energy_platform/bronze/s3.py:77`–`:78`; memory/file implementations `energy_platform/bronze/capture_log.py:112`–`:113` and `:150`–`:155`.

The attempt number is computed as `len(existing)+1` from a list, and the log write is an unconditional PUT to the resulting shared key. There is no atomic reservation, conditional create, or conflict retry. A controller duplicate, manual job, backfill or correction overlap can give two successful writers the same capture ID.

**Reproduction:** two threads both finish their list before either writes; their fetched bodies differ. Both calls return `created=true`; both report the same capture ID but different hashes. Two blobs exist, while only **one capture-log entry** remains discoverable. The barrier changes only scheduling, not the lookup or write behavior. The S3 path has the same unconditional write; a live S3 collision was deliberately not induced.

**Impact:** the older capture's log/provenance is replaced and its content-addressed blob is orphaned. Ledger references can then resolve to a different payload than the one a worker acknowledged. Even where bucket versioning retains old object versions, this reader/reconciler does not enumerate those versions to recover the lost entry.

**Recommendation:** make capture-log creation collision-safe without adding a database dependency to capture: use atomic conditional writes with retry or unique immutable attempt IDs plus an explicit ordering rule. Verify parallel writers against an isolated S3-compatible store. CronJob `Forbid` is not a transaction or a guarantee against all duplicate/manual/other-job execution.

### DC-07 — P1: full replay restores known-invalid deleted data and still passes the restore drill

**Evidence:** `energy_platform/runtime/drill.py:124`–`:153` reprocesses every distinct capture; `:263`–`:290` permits every extra rebuilt version and describes it as pending live work. There is no persisted invalidation decision applied by this path. `docs/07-operations.md:240`–`:245` records deletion of **6,048 known-wrong T2 rows** and explicitly warns not to replay the 22 September runs. The same runbook at `:395`–`:410` acknowledges that the deleted versions reappear as successful-drill extras.

**Reproduction:** in a memory-only system, process one capture and then simulate the reviewed deletion by clearing its Silver rows while preserving Bronze and the ledger. Run the production `restore_drill` function into a fresh memory store. It reports **OK**, with `extra_versions=192`, while the new canonical view contains the 192 removed observations again. The message claims live had unprocessed captures even though the run had already been processed and its output intentionally removed.

**Impact:** the drill proves preservation of live versions, not preservation of live correctness decisions. A full Bronze rebuild can reinstate the documented wrong-date T2 values as current data. This is a **disclosed but unresolved operational gap**; it is not evidence that the backup bytes are missing, and the drill itself writes only to scratch.

**Recommendation:** preserve invalidation/quarantine decisions as durable replay inputs, keyed at least by capture/derivation and reason, and apply them during every replay/restore. Classify extra rows against actual pending work and invalidation records. Require restored canonical output to exclude known-bad observations before treating a drill as safe restoration evidence. Keep the raw evidence immutable.

### DC-08 — P2: freshness counts historical values from other targets/versions as current target coverage

**Evidence:** `energy_platform/store/postgres.py:663`–`:688` queries the full `observations` table, grouping only by dataset/transport and delivery start. It does not select current rows, target lineage, settlement source version, dimensions, resolution or the required metric set. The memory implementation at `energy_platform/store/memory.py:392`–`:418` has the same semantics. `energy_platform/runtime/freshness.py:56`–`:97` applies those counts to the current civil day/hour. This differs from the current-view wording in ADR-037 and the owning-metric completeness requirement in `docs/01-data-scope.md:103` and `:161`.

**Reproductions:** (a) write a non-NULL observation, then a newer NULL correction for the same identity: current has zero non-NULL values but `count_periods` reports one observed period. (b) write 96 daily settlement version-0 periods and **no monthly-target run or version-1 row**, then compute the monthly target's freshness: it reports `complete`, 96/96, entirely from version 0. Both reproduced on PostgreSQL. The second target actually requests the previous month (`targets/ote_imbalance_settlement_monthly/manifest.yaml:36`–`:37`), while the status calculation evaluates today's day. Final monthly version 2 shares the same problem.

**Impact:** unavailable data can appear complete or fresh because another metric/version/target once supplied a non-NULL value. The monthly/final targets cannot currently receive a meaningful publication SLA from this day/hour-only model. Seven deployed target definitions must therefore be distinguished from seven producing, correctly monitored data streams; zero-run monthly targets are not proved operational merely by shared-dataset freshness.

**Recommendation:** define freshness against each target's requested delivery partition, owning metrics, resolution and source-version scope, using eligible current observations and lineage. Model monthly offsets and publication deadlines explicitly. Add cross-target isolation, NULL withdrawal, missing-metric and month-publication cases to freshness tests. Do not “fix” the symptom by widening alert tolerances.

## Strengths supported by code and independent evidence

- Capture and processing are genuinely separated. `runtime/capture.py` persists raw data before ledger acknowledgment; initial-capture database-outage recovery is implemented and tested. DC-01 concerns the unhandled correction variant of that otherwise sound design.
- Normal claim replacement uses a monotonic fence, and PostgreSQL commits lock the run under that fence before inserting observations/events and changing state (`store/postgres.py:335` onward). The correction race does not negate the successful ordinary stale-claimer protection.
- Observations preserve `source_version`, `contract_version`, derivation, raw reference, payload hash, fetched/processed timestamps and source publication time separately. Numeric storage is PostgreSQL `numeric`; valid time is an aware half-open `tstzrange`.
- Native interval and decimal handling is careful: `contracts/intervals.py:85`–`:129` derives day lengths from the source timezone and maps period indices; `contracts/decimals.py:25` onward declares the separator explicitly and preserves blank/NULL versus zero and negative prices. The independent fixture arithmetic confirms the sampled intended output, including the repeated autumn hour and skipped spring hour.
- Unit labels are explicit in the metric registry and manifests; MW load is separated from MWh volume and settlement prices keep CZK/MWh. T1/T2 comparison tolerances are explicit in `mapping/reconcile.py`. The ownership defect is in stored-current selection, not in an absence of an ownership specification.
- Backfill and replay are separate verbs; replay does not fetch. The gap detector uses source history limits and records unrecoverable missing captures rather than fabricating payloads (`runtime/gaps.py`).
- HTTP capture has bounded retry policy and streamed response limits; Bronze is content-addressed and verifies hashes on reads with a hot/cold fallback. The concurrency defect concerns log creation, not content hashing.
- The source evidence and operations history acknowledge synthetic fixtures, source limitations and actual incidents. That candor is useful. It should be reflected in acceptance claims: an independently matched synthetic golden is strong implementation evidence, but not independent proof of a provider's publication timing or live correctness.

## Boundaries and unverified items

This sub-audit did not mutate live infrastructure, inspect secret values, induce live concurrency, stop a node, perform a production restore, or obtain new legal/source-cadence guarantees. The parent review owns current read-only live/GitHub checks. The local native-fixture cross-check establishes arithmetic consistency for the committed samples, not every possible provider format or publication state.

The accepted contracts/ADRs, current Phase 9 context, relevant tests and implementations were used to distinguish intended design from executable behavior. This report does not claim that documentation alone demonstrates HA. Source-drift and triage behavior is assessed in the companion agentic-engineering report; it should be read alongside these recovery and canonical-selection findings.

The remediation order should begin with DC-03/current ownership and DC-04/occurrence identity, then the DC-01/DC-02 correction handoff, DC-06 immutable log creation and DC-07 replay-safe invalidation. DC-05 replay reclamation and DC-08 truthful freshness are necessary to make those repairs operationally recoverable and observable. These are recommendations only; no fix was implemented in this review.
