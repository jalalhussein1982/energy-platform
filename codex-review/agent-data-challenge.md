# Independent challenge: scheduling, replay identity and recovery

Reviewed 2026-09-25 against checkout `bc87c585ce8a61be2995d0b0b1b283f87c2032a6`. Read-only review of source, accepted decisions, the draft final report, and the review's existing synthetic and live evidence. This reviewer did not execute the probes again, run costly suites, contact sources, or change the application. Only this report was written.

The four proposed findings survive challenge, with material qualifications. They establish defects in recovery identity and verification; they do **not** establish that existing production energy values are wrong. Suggested priorities: P1 for unchanged derivation identity across implementation fixes; P2 for the schedule mismatch and both restore-drill defects. These are technical priorities, not assertions of a currently ongoing incident.

## 1. Captures use wall-clock starts while gap detection expects exact cron instants

**Verdict: valid. P2.** A normal delayed Job start produces a successful capture that does not satisfy its expected scheduled slot. The detector marks a second run missing; backfill can fetch the same delivery day again.

Source:

- `energy_platform/cli.py:317-343`: `--scheduled-for` is optional; live capture defaults to `datetime.now(UTC)`. This timestamp is taken **before** `_jitter`, so injected jitter itself is not the cause; Job startup latency and the unrounded wall clock are sufficient.
- `deployment/helm/energy-platform/templates/cronjob-target.yaml:17-23`: scheduled capture arguments omit `--scheduled-for`; the template separately schedules backfill.
- `energy_platform/runtime/gaps.py:79-92`: capture entries and runs are indexed by exact `scheduled_for`; expected cron instants use exact lookup. `:106-114` creates a missing-capture run for a nonmatching instant.
- `energy_platform/runtime/backfill.py:9-17`: every eligible missing-capture run is fetched, subject to the limit.
- ADR-031 `:20-34` says the tolerance absorbs late starts. It only delays classification in the implementation; it does not reconcile the mismatched identities.

Evidence: `evidence/schedule_probe.py` and `evidence/schedule-probe-postgres.json` show a processed capture at `22:15:25.693263`, a separate `22:15:00` missing-capture run after the tolerance, and one successful additional backfill that raises the Bronze capture count to two. The report also exists for MemoryStore. The fixture transport means this is an unnecessary fetch invocation, not an actual request sent to OTE during the probe.

Independent live support is narrower: `evidence/live-process.log` records a successful process at `23:15:25.693263`; `evidence/live-gaps-summary.json` contains 29 exact-minute missing-capture results in an earlier window. Those two saved outputs do not pair every missing slot with a corresponding successful capture, so do not claim all 29 were independently proven false gaps. The synthetic example and source establish the mechanism.

Impact: redundant source requests and ledger work; degraded missed-run diagnostics. The evidence does not show duplicated canonical values, present loss of energy observations, or a demonstrated outage. A deterministic intended schedule identity must be shared by capture and gaps; merely waiting longer cannot solve it.

## 2. Restore compares a shared dataset before all its targets have been rebuilt

**Verdict: valid; “8916 rows lost during restore” would be overstated. P2.** The first fresh rebuild reports a false failure because the per-target comparison covers other targets' rows. The completed first pass has already rebuilt those rows; the same scratch database passes the second invocation.

Source:

- `energy_platform/runtime/drill.py:115-130` and `:208-216`: both Silver comparison sides select by dataset and transport, not originating target. `_live_side` additionally applies the current target's replica time bound to those shared rows.
- `energy_platform/store/postgres.py:686-704`: the real PostgreSQL iterator confirms the dataset/transport-only query; this is not peculiar to MemoryStore.
- `energy_platform/runtime/drill.py:278-310` compares immediately after rebuilding one target, and `:348-359` performs that entire sequence separately for each manifest. Earlier failure reports are not recomputed after later targets finish.
- `targets/ote_imbalance_settlement/manifest.yaml:39-40`, the monthly manifest `:39-40`, and final manifest `:40-41` all declare `ote.imbalance_settlement` through SOAP. This is an actual supported target combination.

Evidence: `evidence/recovery_probes.py` uses the committed daily and monthly manifests with their committed synthetic fixtures. `evidence/recovery-probes-postgres.json` reports 288 scratch versions versus 9204 live versions when checking daily first, hence 8916 “missing”; after monthly is processed, scratch contains all 9204. Repeating the same drill on that scratch store passes. This control falsifies physical loss as the explanation. Monthly's “ahead by 288” message also misattributes the other target's rows to pending work.

The saved live drill passed, but both monthly and final targets had zero replica captures and zero processed runs while their reports each claimed 576 Silver versions belonging to the shared dataset (`evidence/live-restore-log.txt`). That is evidence that the per-target report is misleading; it is **not** evidence that production already hit the populated-monthly failure.

Impact: a recoverable archive can fail the automated fresh-schema drill and alert as data loss; the result depends on ordering and preexisting scratch contents. Restore can reproduce the records despite failing its validation. Comparison needs target-scoped lineage, or complete group reconstruction before a consistent group-level comparison; the current mixed scope is the defect.

## 3. Current manifests cannot reproduce every historical derivation from Bronze alone

**Verdict: valid; “all recovery fails after a manifest change” would be overstated. P2.** An ordinary mapping change creates a new derivation as designed, but the fresh-schema drill only runs the current manifest while demanding every historical derivation held by live.

Source:

- `energy_platform/cli.py:449-455` loads the current target manifests; no historical derivation configuration is supplied to the rebuild.
- `energy_platform/runtime/drill.py:159-189` processes current runtime mapping and one current derivation across the capture history.
- `energy_platform/runtime/drill.py:93-95` includes derivation identity in each comparison fingerprint, and `:298-310` demands the complete live fingerprint set.
- `energy_platform/store/protocol.py:97-110` derives identity from the current mapping and platform version.
- ADR-023 `:23-41` requires a changed implementation/mapping to append a distinguishable version; the broad Bronze-only claim appears in `docs/overview/final-report.md:9,31,57`.

Evidence: the mapping-revision scenario in `evidence/recovery_probes.py` adds only `DisplayNote` to `ignore_fields`, then replays the existing payload. This harmless change leaves the energy values unchanged but changes the derivation from `744622420669ce10` to `92a0ba24970d530f`. Live holds 384 versions across the two derivations. The fresh rebuild produces 192 current-derivation versions and reports the 192 older ones missing (`evidence/recovery-probes-postgres.json`).

Qualification: the probe uses an in-memory model copy for its manifest revision rather than editing a manifest file; the changed field is a normal mapping field, and it isolates the identity problem without changing source bytes or values. This proves the historical-version mismatch, not a wrong current value. A database restored from a base backup/WAL can retain the old rows and derivation metadata; that is a distinct recovery path, so this is not proof that PITR is broken. It also does not show current production has already accumulated these two derivations.

Impact: exact historical Silver lineage is not reconstructible by the implemented **current-manifest Bronze-only** path after legitimate evolution; the automated fresh-schema comparison fails even for a value-preserving update. ADR-036 `:71-76` originally describes comparison of current Silver, whereas the implementation compares all versions. The promised recovery product must be explicit: retaining historical executable/configuration identities for historical reconstruction is different from rebuilding current outputs and validating those.

## 4. Core-only fixes retain derivation identity and replay leaves old values in place

**Verdict: valid under the current build path. P1.** A correction to parsing/mapping code that leaves the manifest and the unchanged package version alone reuses the old upsert key. Replay executes the fixed mapping, but its corrected observation conflicts with the earlier version and remains a no-op.

Source:

- `energy_platform/__init__.py:7` and `pyproject.toml:3` remain `0.0.1`.
- `energy_platform/store/protocol.py:97-110` and `energy_platform/parse/generic.py:63-65` use that package version, not the deployed image digest or commit, in the derivation identity.
- `energy_platform/contracts/observation.py:150-170` defines the version key and the four hash inputs; implementation source content is absent.
- `.github/workflows/deploy-demo.yml:41-50` tags builds by Git SHA; `deployment/image/Dockerfile:29-35` copies the code without injecting that identity. A new immutable image therefore does not by itself change the derivation.
- `energy_platform/runtime/process.py:82-125` computes and commits mapped observations; `energy_platform/store/postgres.py:389-431` uses existing version identity and counts only new versions/occurrences.
- ADR-023 `:14-18,23-41,54-57` expressly names a code bugfix and repair replay as the reason for derivation identity.

Evidence: `evidence/derivation_probe.py` patches the mapping result in memory to simulate a core-only correction. `evidence/derivation-probe-postgres.json` shows the same derivation `744622420669ce10`, zero inserts and unchanged synthetic price `170.13`. Its positive control changes the package version to `0.0.2`; a new derivation is generated, 192 rows are inserted, and the corrected synthetic price becomes `171.13`. The unchanged result is therefore the identity collision, not failure to invoke the corrected code.

Qualification: the correction is deliberately synthetic; it is not evidence that `170.13` or any live value is wrong. Correctly bumping the platform version before every output-affecting release prevents the demonstrated collision. The claim is that the present implementation and release path do not make that invariant true automatically; Git history for `energy_platform/__init__.py` shows only its initial skeleton commit. A manifest change also changes the identity, so do not say all replay is broken.

Impact: the documented repair procedure can silently keep incorrect historical values after a real core fix unless the release also changes derivation identity. The fixed output needs a distinct derivation while exact retries remain idempotent. This is separate from finding 3: fixing identity makes version history correctly distinguishable, but the Bronze-only rebuild must then know how to handle that history.

## Assessment of the supplied evidence

The review's PostgreSQL backend helper creates fresh schemas only on its temporary Unix-socket PostgreSQL and refuses other DSNs (`evidence/probe_store.py`). The probes reuse fixture transports and synthetic repository fixtures; they do not demonstrate source mispublication. Both MemoryStore and PostgreSQL outputs were inspected, but their execution was performed by the parent review, not repeated here. The existing successful live drill is real positive evidence for the history and target population it exercised. It does not falsify the evolution and shared-dataset counterexamples above.

No application fix, deployment action, commit, database mutation, new source request, or test-suite execution was performed by this challenge reviewer.
