# ADR-036 — Object stores per profile, Bronze replication, and Postgres backups without a custom image

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-22 |
| Resolves | D-3 (`02-architecture-decisions.md` §4.2); amends ADR-002 "pgBackRest/WAL-G with PITR" (tooling, not the guarantee); refines ADR-021 §1 (tiering job shape) and ADR-028 §3 with the V-12/V-13 outcomes |
| Supersedes | — |
| Amended | 2026-09-23, amendment 1 (below): §4 `statefulset` backup footprint bounded — compressed WAL shipped and pruned, daily base backup, drill fetches WAL from the base's start segment · 2026-09-24, amendment 4 (below): the `local` profile's servers are RustFS after MinIO's images were withdrawn; bucket bootstrap through the platform's client |

## Context

ADR-002 fixes the guarantees: Bronze immutable, versioned, with an independent copy in a second
failure domain; Silver authoritative in PostgreSQL with PITR; a restore drill that runs. ADR-021
made tiering a platform `rclone` job. ADR-028 named the demo pair. The verification runs answered
what each store can actually enforce:

- **V-12, Hetzner Object Storage (store A):** versioning; bucket-level Object Lock enforced
  (COMPLIANCE ignores the bypass flag); STANDARD is the only storage class; the lifecycle API
  accepts anything without validation; a deny-`DeleteObject` bucket policy is stored but **not
  enforced** against the owning credentials, and there is one credential set per project.
- **V-13, OCI Object Storage (store B):** versioning over S3; no S3 Object Lock; a native
  **retention rule** is enforced on delete and overwrite over both APIs; **retention rules and
  versioning are mutually exclusive**; `aws-chunked` uploads are rejected; `rclone sync` A → B
  with `check --download` gave 0 differences.
- **V-6, reference RGW/Swift:** the record that shaped ADR-021 (STANDARD-only, lifecycle
  no-op), kept as history; nothing of ours runs there (ADR-028).
- ADR-002's tool names (pgBackRest, WAL-G) both require the binary inside the Postgres
  container, i.e. a custom Postgres image, which nothing else in the platform needs.

## Decision

1. **Per-profile store table (D-3).**

   | Profile | Store A (hot, capture writes) | Store B (independent copy, replication writes only) | Immutability control |
   |---|---|---|---|
   | `local` | RustFS 1 in the chart (`objectstore.local.enabled`; MinIO until amendment 4), bucket created with Object Lock, versioning on | RustFS 2 in the chart, plain bucket | Object Lock on A; B is a copy target |
   | `tenant` (scenario A) | the platform's S3 endpoint by values | a second endpoint by values (another site or provider) | Object Lock where offered; otherwise the ADR-021 compensating control (copy-verify under the ledger, never overwrite by key) |
   | `own-cluster` / demo | Hetzner Object Storage, versioning **on**, bucket-level Object Lock COMPLIANCE `bronze.retention.days` (Terraform `storage` module over the `aws` provider) | OCI Object Storage Frankfurt over the S3-compatible endpoint, **versioning OFF, retention rule** `replica.retentionDays` (Terraform `oci` provider) | Object Lock on A; retention rule on B — the bucket-policy half of the ADR-021 fallback is **not** used (V-12: unenforceable against the owner) |
   | reference (record only) | CESNET RGW | MetaCentrum Swift | V-6; no release of ours |

2. **Client behaviour fixed by the probes.** The platform S3 client keeps signing the **whole
   payload** (`x-amz-content-sha256` = SHA-256 of the body, never `aws-chunked`; V-13). It
   tolerates an error body with an empty `<Message></Message>` (V-12). `bronze.tiering.mode` on
   the demo is `none` (default) or `move`; **`lifecycle` is refused by the demo values** because
   lifecycle acceptance proves nothing on that gateway. The `storage-probe` hook (ADR-021 §3,
   ADR-025) probes by `PUT` + `HEAD` of one object with the configured class, never by reading
   the lifecycle configuration.

3. **Replication is `rclone copy`, never `sync`.** A `replicate` CronJob copies `bronze/` and the
   backup prefix from A to B with `--checksum --immutable` (an object that differs at the same key
   is an error, not an overwrite; nothing is ever deleted on B). Provider `Other` for OCI. The job
   logs `rclone check` differences; the freshness exporter does not know about it — a failed Job
   is the alert (`kube_job_status_failed`). Tiering in `move` mode is `rclone move` of
   `bronze/blobs/` older than `afterDays` to the cold location with identical keys (ADR-021 §1);
   capture-log entries stay hot; the read path already tries hot then cold; no library verb.

4. **Postgres backup per `postgres.mode` (amends ADR-002 tooling).**
   - `statefulset`: `archive_mode = on`, `archive_command` copies each WAL segment to a
     `wal-archive` volume shared with the backup job; a `pg-backup` CronJob takes a
     `pg_basebackup` (tar, compressed, `-X none`) and ships base + WAL archive to store A under
     `bronze.backupPrefix` with `rclone` (`--immutable`); the replication job mirrors that prefix
     to B. This is base-backup + continuous WAL archiving, i.e. PITR, with the tool already in
     the design and the stock `postgres:16` image by digest. Retention of old base backups is a
     documented manual step (deletion is Level 3).
   - `cnpg`: the operator's own object-store backup (Barman) to store A; the chart renders the
     `Backup`/`ScheduledBackup` objects only behind the flag.
   - `external`: the provider's PITR; the chart documents the expectation and runs the drill
     against a scratch database the operator provides.

5. **Restore drill reads B.** The `restore-drill` CronJob restores the newest base backup and
   WAL from **store B** into a scratch Postgres inside the Job pod, then runs
   `energyctl restore-drill`: migrate the scratch schema, `reconcile` over the full Bronze history
   read from B (ADR-024 §2 ledger rebuild), `replay` every run (ADR-021 §5 cold-backed replay),
   and compare with the live database: run counts by state, current Silver row count, an
   order-independent checksum over (observation identity, value). Any difference fails the Job.
   Measured wall clock is the RTO figure `docs/07-operations.md` quotes; nothing is assumed.

6. **Residency** is a chart value asserted in every values file (`residency: CZ` production,
   `DE` demo, `local` for kind) and rendered as a label on every workload so the deviation is
   visible, not hidden (ADR-028 §4).

## Rationale

Each row of the table names the control that was **shown** to hold on that store, and the
client changes are the two facts the probes produced. Replication by `copy --immutable` rather
than `sync` is what "never delete on B" means mechanically. On backups, the guarantee (PITR,
drilled) is kept while the tool is the one already inside the design; the cost if that is wrong
(a team standardised on pgBackRest) is a values switch to `cnpg` or `external`, not a schema or
chart change.

## Rejected

- **Object Lock on B via OCI** — not offered over S3 (V-13); the retention rule is the native
  equivalent and is enforced over both APIs.
- **Versioning on B** — mutually exclusive with the retention rule on OCI; adds nothing because
  Bronze is content-addressed and never overwritten by key.
- **Bucket policy denying `DeleteObject` as the A fallback** — stored but not enforced against
  the single credential set (V-12).
- **`rclone sync` for replication** — deletes on B what disappears on A; the opposite of a copy
  in a second failure domain.
- **pgBackRest / WAL-G binaries in a custom Postgres image** — a second image to build, pin and
  scan for one binary; the stock image plus WAL archiving reaches the same guarantee.
- **Native bucket replication features** — provider-specific, absent on one side of every pair
  we have.

## Consequences

- `02` §4.2 D-3 → "resolved by ADR-036"; ADR-002 backup table's Postgres row reads "base backup +
  WAL archive shipped by `rclone` (statefulset), CNPG Barman (cnpg), provider PITR (external);
  drilled" (reconciliation edit).
- Chart values: `bronze.{endpoint,bucket,allowedHosts,retention,tiering,replica,backupPrefix}`,
  `objectstore.local.enabled`, `postgres.backup.schedule`, `drills.restore.{enabled,schedule}`,
  `residency` (required).
- Library: `bronze_from_env` (Phase 5 plan P5-D4), `storage-probe`, `restore-drill` verbs; the
  S3 client's empty-`Message` tolerance gets a test.
- Terraform `storage` module encodes the demo row (ADR-035 §3).
- Devil's advocate: `archive_command` to a volume makes the WAL archive only as durable as that
  volume until the next backup run; the backup schedule (default every 15 min, matching the ADR-002
  Silver RPO) bounds the exposure, and Bronze — the irreplaceable tier — is not on this path.

## Amendment 1 (2026-09-23) — bounded backup footprint

**Context.** Reviewing the demo hand-over found that §4 as built does not bound its own
footprint. `archive_timeout = 300` closes a 16 MiB segment every five minutes whenever anything
was written (the ingestion CronJobs write every few minutes), about 4.5 GiB of WAL a day; the
`wal-archive` volume was only ever copied from, never pruned, and on k3s `local-path` the 2 Gi
request is not enforced, so the demo's shared 10 GB volume would fill in about two days and
stop Postgres. The base backup ran every 15 minutes (96 a day). Every object shipped to store A
carries the 90-day COMPLIANCE default retention and is mirrored to B under its retention rule,
so none of it could be deleted for 90 days. The restore drill fetched the whole WAL history on
every run. The local measurements (docs/07 §5: 16 segments, 192 MiB in ~25 minutes) agree;
kind never showed the problem because nothing ran long enough and MinIO's lock there is one day.

**Decision (replaces the `statefulset` bullet of §4; the guarantee — PITR, drilled — is kept).**

1. `archive_command` compresses each segment with `gzip -n` (no name, no timestamp: the same
   segment always produces the same bytes) into `<segment>.gz.part` and renames it to
   `<segment>.gz`; if `<segment>.gz` already exists with the same content, archiving succeeds
   (a retry after a crash), otherwise it fails. A segment closed early by `archive_timeout` is
   mostly zero pages and compresses to a small fraction of 16 MiB.
2. A `pg-wal-ship` CronJob (`postgres.backup.walSchedule`, default every 10 minutes) runs
   `rclone move` from the `wal-archive` volume to `A:<backupPrefix>/wal/` with `--immutable
   --checksum`: a segment leaves the volume only once it is in A, an object that differs at the
   same key fails the Job, and `*.part` files are never touched. The volume holds only what is
   not yet shipped.
3. The `pg-backup` CronJob takes the base backup only (`postgres.backup.baseSchedule`, default
   daily 02:15, before the 03:17 replication and the 03:30 drill) and writes a `START_WAL` marker
   (the segment named by `backup_label`) next to `base.tar.gz`.
4. The restore drill fetches the newest base and only the archived WAL whose name sorts at or
   after its `START_WAL`; `restore_command` reads `<segment>.gz` or, for an archive written
   before this amendment, the plain segment.
5. RPO for Silver: `archive_timeout` (5 min) + `walSchedule` (10 min) = 15 min, the ADR-002
   target. Base-backup frequency moves only the replay length, i.e. RTO, which the drill measures.
6. *(added 2026-09-23, first demo deploy)* Every archive path carries the cluster's **system
   identifier** (`pg_control_system()`): `<backupPrefix>/<system id>/base/<stamp>/` and
   `<backupPrefix>/<system id>/wal/`. A re-initialised cluster — a fresh deploy, a Bronze-only
   rebuild — restarts WAL names at `…01`; in a shared prefix its first segment would meet the
   earlier cluster's locked object at the same key and every `pg-wal-ship` run would fail
   (`--immutable`), with no way to delete the old object for 90 days. The restore drill takes
   the newest base across system identifiers and that cluster's WAL. This is what pgBackRest's
   stanza and WAL-G's system-identifier check do.

**Consequences.** Base backups and WAL still live 90 days under the store-A lock and in B
(deleting expired ones stays a documented Level 3 step), but the daily volume is one compressed
base plus compressed WAL instead of 96 bases plus raw WAL. The devil's-advocate note in
Consequences now reads: the WAL archive is only as durable as its volume until the next
`pg-wal-ship` run (≤ 10 minutes). Chart values: `postgres.backup.{enabled, baseSchedule,
walSchedule}` replace `postgres.backup.schedule`. Rejected: a shorter per-object lock on the
backup prefix (`rclone --s3-object-lock-*`) — not verified on Hetzner's gateway, and with the
volume bounded the 90-day lock costs little; a separate backup bucket — two more buckets and a
second replication pair for the same effect.

## Amendment 2 (2026-09-24) — RPO per failure domain; the independent copy follows the cadence

**Context.** Review 2 (DEP-01, `codex-review/2026-09-24/04-deployment-and-ha.md`): ADR-002's
table states Bronze RPO ≤ the polling interval and Silver RPO ≤ 15 minutes, and amendment 1
made the Silver figure true — **for the loss of the database node while store A is up**. The
demo replicated A → B once an hour, so for the loss of store A or its provider the independent
copy could be an hour behind, and nothing watched its age: a job that never runs has no
failed-Job metric.

**Decision.**

1. The RPO is stated per failure domain, and each figure names the mechanism that makes it true:

   | Failure domain | Bronze RPO | Silver RPO | Mechanism |
   |---|---|---|---|
   | a worker or a pod | 0 | 0 | Bronze first, fenced commits (ADR-024) |
   | the database node / instance, store A up | 0 | `archive_timeout` + `walSchedule` = 15 min | WAL shipped to A (amendment 1) |
   | store A or its provider | replication interval + copy time | the same (WAL and bases live in A until copied) | `replicate` A → B (§3) |
   | the whole environment (nodes, stores A, identities) | as store A | as store A, plus the Bronze-only rebuild time | store B + the restore drill (§5) |

2. **The replication interval follows the capture cadence.** Demo: `7,22,37,52 * * * *`, seven
   minutes after each 15-minute capture instant so the `check --min-age 5m` covers that
   capture; RPO for a store-A loss = 15 minutes + copy time. The chart default stays hourly and
   says what that means.
3. **Age is watched, not only failure.** Three alert rules over kube-state-metrics'
   `kube_cronjob_status_last_successful_time` (the dependency the drill alert already has):
   `EnergyPlatformReplicationStale` (`bronze.replica.staleAfterSeconds`, demo 45 min),
   `EnergyPlatformWalShipmentStale` (`postgres.backup.walStaleAfterSeconds`, 30 min) and
   `EnergyPlatformBaseBackupStale` (`postgres.backup.baseStaleAfterSeconds`, 2 days). A stale
   copy pages while ingestion looks healthy.
4. **What the drill measures.** Its wall clock is the *replay* duration on warm infrastructure
   (`docs/07` §5.3 states the two phases and the whole Job separately); the RTO for the loss of
   the whole environment is that plus replacement nodes, identities and secrets, and resumed
   schedules — measured only by an exercise that rebuilds them, which the demo has not run.

**Consequences.** `02`'s RPO table carries a dated pointer here; `05` unchanged; `docs/07` §5
names the three rules. Rejected: replicating on every capture (a Job per fetch, and the 5-minute
`min-age` check would never settle) and a replica-age gauge computed by the platform (the
exporter reads Postgres, the copy lives in object storage; kube-state-metrics already knows
when the Job last succeeded).

## Amendment 3 (2026-09-24) — modes without a backup chain refuse the drill

**Finding (review 2 DEP-02).** §4 promised `cnpg` (Barman objects behind the flag) and
`external` (the provider's PITR with an operator-provided scratch database); the chart renders
neither: `cnpg` renders one `Cluster` and no backup object, `external` nothing, while the
restore-drill CronJob still searches B for the `<system id>/base/<stamp>` layout and builds its
scratch DSN from `$POSTGRES_PASSWORD`, which those modes do not supply. A fresh CNPG install
therefore had a drill that could never restore anything, accepted silently at render time.

**Decision.** `drills.restore.enabled` with `postgres.mode` other than `statefulset` **fails
the render** and says why. The `ci/all-flags-values.yaml` render (cnpg) disables the drill for
that reason. The two modes stay selectable for the database itself; their backup and drill
contracts are implemented when a CNPG cluster exists to test against (own-cluster scenario B),
together with a version-bearing `imageName`/`imageCatalogRef` for the operator's admission
(review 2 DEP-02). Until then the README's "deliberately not built" table names both.

**Proof:** `tests/harness/test_chart.py::test_the_drill_refuses_database_modes_without_a_backup_chain`.

## Amendment 4 (2026-09-24) — the local profile's servers after MinIO

**Context.** On 2026-09-24 `make local-up` on a fresh kind cluster failed at the image pull:
MinIO's community images (`quay.io/minio/minio`, `quay.io/minio/mc`, both pinned by digest) are
no longer served by quay.io or Docker Hub, and `github.com/minio/minio` is archived (`07` §8.3).
The digest pins did their job — nothing else was pulled in their place — but a pin cannot keep
a publisher from withdrawing an image. The `local` profile row of §1 named a product that no
longer exists as a pullable artefact; the demo (Hetzner, OCI) is unaffected.

**Decision.**

1. **The `local` profile's two stores are RustFS 1.0.0** (`docker.io/rustfs/rustfs@sha256:8cc98017…`),
   chosen **by probe, not by README** (`docs/plans/phase-12.md` P12-D1): a scratch script ran the
   candidate in Docker and exercised, with the AWS CLI, rclone and the platform's own
   `ObjectStore` client, everything the profile relies on — create-bucket with Object Lock,
   versioning, PUT with COMPLIANCE retention headers and HEAD returning the lock, DELETE of the
   locked version refused (`AccessDenied`), the old version readable and kept after an
   overwrite, ListObjectsV2 paging, `x-amz-storage-class` on PUT, `If-None-Match: *` honoured
   (the ADR-024 am.3 create-only PUT), `rclone copy --immutable` and `check` A → B. All 23
   steps pass (`07` §8.4). The first candidate to pass every step was the one; versitygw and
   SeaweedFS were not needed.
2. **Chart shape unchanged** (P12-D3): the same two StatefulSets, Services and port 9000, the
   same PVC sizes, and the same Secret keys (`BRONZE_*`, `BRONZE_REPLICA_*`) as the servers'
   root credentials — so the rclone aliases, the NetworkPolicies, the storage probe and the
   drills are untouched. What changed is the image, its env (`RUSTFS_VOLUMES=/data`, console
   off, logs to an emptyDir under the read-only root filesystem) and the readiness path.
3. **Bucket bootstrap through the platform's client** (P12-D2): `energyctl bucket-init` — three
   new verbs on `fetch.objectstore` (`bucket_exists`, `create_bucket(object_lock=…)`,
   `put_bucket_versioning`) — replaces the `mc` job; the hook runs the platform image, creates
   bucket A with Object Lock and versioning and bucket B plain, idempotently. One fewer
   third-party image; the same signed client the platform trusts; reusable for a tenant's
   first deploy.

**Residual.** RustFS is a young project (1.0.0, 2026-09); the `local` profile is a laptop test
bed, not a production store, and nothing of the demo's or a tenant's data depends on it. A
withdrawal can happen again to any pinned image; the answer is the same probe, not a looser pin.
HEAD does not echo `StorageClass` for STANDARD objects (as S3 itself does not); the tiering
probe (ADR-021 §3) treats an absent class as STANDARD.

## Verification refs

`07` §8.4 (the probe transcript and the clean-clone gate after amendment 4);
`tests/fetch/test_objectstore.py::test_bucket_init_creates_a_locked_versioned_bucket_once`;
`tests/harness/test_chart.py::test_local_object_stores_are_rustfs_with_the_bucket_init_hook_on_the_platform_image`.

`00-assumptions.md` §5: 2026-09-22 · V-12 · CONFIRMED; 2026-09-22 · V-13 · CONFIRMED;
2026-09-19 · V-6 · CONFIRMED (reference record); 2026-09-19 · V-10 · CONFIRMED (no managed
Postgres; `statefulset` is the mode the drill exercises first).

## Amendment 5 (2026-09-25) — what the Bronze-only rebuild guarantees, and how the drill compares

**Findings (review 3 R5 and R6, `codex-review/01-deep-review.md`).** §5 promised "an
order-independent checksum over (observation identity, value)"; the implementation compared
every stored version *with its derivation id*, selected by dataset and transport, and compared
each target right after its own rebuild. Two consequences, both reproduced on PostgreSQL: (R5)
three committed targets share `ote.imbalance_settlement`/SOAP, so the first target's comparison
read its siblings' rows as 8 916 missing versions on an empty scratch store and passed on a
warm one — the drill's verdict depended on order and on what the scratch already held; (R6) an
ordinary mapping revision (an unused `ignore_fields` name) is a new derivation by design
(ADR-023), and the current-manifest rebuild could not produce the 192 versions under the old
one, so a value-preserving change failed the drill. No replica holds old code; demanding its
output from a current-code rebuild is a guarantee nobody can keep.

**Decision.**

1. **The cohort is rebuilt first.** `restore_drill` rebuilds every committed target in the
   scratch store (reconcile over the full replica history, every distinct capture of a run
   oldest first, amendment 2 of ADR-023) and only then compares, target by target.
2. **Comparison is scoped to the target's own lineage**: the rows the target's own attempts
   produced, streamed; a version live attributes to this target and the rebuild to a sibling
   sharing the dataset and transport is reproduced, counted as such, never missing. A target
   that never captured reports no versions, not its siblings'.
3. **The rebuild guarantees values, not derivation ids.** Fingerprints are (observation
   identity, payload sha256, value). Per (identity, payload) live holds within the replica
   bound, the rebuild must reproduce the value of live's **newest derivation** for that pair
   (by `derivations.registered_at`). A pair the rebuild lacks entirely is `missing` — loss; a
   pair the rebuild holds with another value is `diverging` — the running implementation no
   longer produces live's value from that payload, an un-replayed correction or a regression;
   both fail the drill and are named separately. Versions under retired derivations are
   `historical`: counted, named in the report, not compared. The physical backup keeps them,
   and the drill's first phase (against the restored database) is what proves that backup;
   the Bronze-only phase proves that the code in production reproduces the data in production.
4. §5's sentence "run counts by state, current Silver row count, an order-independent checksum
   over (observation identity, value)" reads: processed-run counts; the lineage-scoped value
   fingerprints of decision 3, with `missing`, `diverging`, `extra` (the rebuild ahead of live),
   `lagging` (newer than the replica), `historical` and `sibling` counts in every target's
   report.

**Consequences.** After a value-changing release the nightly drill fails with `diverging` until
the affected derivation is replayed (`energyctl replay --derivation`, ADR-016 §4) or the
captures invalidated (ADR-038) — that is the signal wanted, not noise: production disagrees
with the code it runs. A value-preserving release, and any manifest revision that keeps values,
passes with its old versions reported as historical. `docs/07` §5 and the final report state
the guarantee in these words.

**Proof (memory and PostgreSQL):** `tests/runtime/test_review3.py::test_r5_…`,
`test_r6_…`, `tests/store/test_review3_drill.py` (the reviewer's daily+monthly fixtures on an
empty scratch schema in either order; a target with no captures reports none of its siblings'
rows; the `ignore_fields` revision passes with 192 historical versions; a value-changing
implementation without a replay is `diverging` and fails, after the replay passes with the old
versions historical); `tests/runtime/test_drill.py` (loss and a tampered value still fail). The
reviewer's `recovery_probes.py` no longer reproduces either defect.
