# ADR-021 — Bronze cold tier as a platform tiering job

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | D-8 (`02-architecture-decisions.md` §4.2); amends ADR-002 "lifecycle to cold tier" |
| Supersedes | — |

## Context

ADR-002 assumed the Bronze cold tier is an S3 lifecycle transition to a cheaper storage class. On the reference S3 store (CESNET, Ceph RGW) V-6 showed that only `STANDARD` exists: every other class on upload returns `400 InvalidArgument`, while the lifecycle API **accepts a transition to any class name, including a non-existent one, without validation**. A lifecycle-based cold tier on such an endpoint installs cleanly and never moves a byte. Azure Blob (scenario C) has no S3 lifecycle at all. Pricing on the reference environment is by quota, so the cold tier is not needed there; it is needed on ČEZ's platform (Glacier/Archive in C, tape or a cheaper Ceph pool in A/B).

## Decision

1. **Tiering is a platform job.** A `bronze-tier` `CronJob` (ADR-003 rev. shape, ledger-tracked) moves capture blobs older than `bronze.tiering.afterDays` from the hot bucket to a cold location with `rclone`, the same tool used for the independent copy. Object keys are identical in hot and cold (content-addressed); a Bronze read tries hot, then cold. The capture-log entry gains `tier: hot | cold`. Object lock/versioning are applied on the cold side too.
2. **Three modes**, one Helm value `bronze.tiering.mode`:
   - `none` — everything stays hot (default for `local` and for the reference `tenant` deploy).
   - `move` — job moves to `bronze.tiering.coldEndpoint` / `coldBucket` (any S3, Swift, Azure Blob, GCS that `rclone` speaks). This is the portable default for A/B/C.
   - `lifecycle` — bucket lifecycle transition to `bronze.tiering.storageClass`, allowed **only where the probe in (3) passes**.
3. **Probe before trust.** A `helm test` hook uploads one object with the configured storage class and asserts `HEAD` reports that class; `400 InvalidArgument` (empty message) or a `HEAD` reporting `STANDARD` fails the deploy. The same probe runs in the nightly restore drill so a gateway change is detected.
4. **Cold ≠ independent copy.** Bronze is irreplaceable; old captures must still exist in two failure domains. The replication job (ADR-002) mirrors both hot and cold; tiering never reduces copy count.
5. **Restore path.** `energyctl replay` reads from cold transparently; RTO for cold-backed replay is measured in the restore drill and documented, never assumed.

## Rationale

The platform owns the guarantee ("older captures are on cheaper storage and still restorable"), so the platform must own the mechanism. A bucket feature that silently no-ops on the reference environment and does not exist on Azure cannot carry that guarantee. `rclone` is already a dependency of the design, so the cost is one more `CronJob` template and one probe.

## Rejected

- Lifecycle transition as the only mechanism (silent no-op on Ceph RGW without configured classes; absent on Azure Blob).
- Trusting `put-bucket-lifecycle-configuration` success as evidence a class exists (V-6: it accepted `DEFINITELY_NOT_A_CLASS`).
- Asking CESNET for tape as an S3 class (their archive is a separate service and endpoint, i.e. `move` mode anyway).
- Letting the cold copy be the only copy of old data (violates ADR-002 independent-copy rule).

## Consequences

- `02` ADR-002: "lifecycle to cold tier" → "tiering job (ADR-021); lifecycle only where probed". D-8 resolved.
- `03` Phase 5: `bronze-tier` CronJob, tiering probe in `helm test`, cold read path in restore drill. Phase 2: `bronze/` read path tries hot then cold; capture log gains `tier`.
- `00` §5 V-6 → CONFIRMED: the open question (does a cold class exist) is answered — it does not — and the design no longer depends on it.
- Devil's advocate: a `move` job is a second writer to Bronze. Mitigation: it moves by copy-verify-delete with checksum match, under the ledger, and never touches the capture log's `sha256`.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-6 · CONFIRMED (storage-class probe: STANDARD only; lifecycle accepts unknown class names; Swift second endpoint verified).
