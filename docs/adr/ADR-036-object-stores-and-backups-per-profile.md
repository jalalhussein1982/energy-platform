# ADR-036 — Object stores per profile, Bronze replication, and Postgres backups without a custom image

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-22 |
| Resolves | D-3 (`02-architecture-decisions.md` §4.2); amends ADR-002 "pgBackRest/WAL-G with PITR" (tooling, not the guarantee); refines ADR-021 §1 (tiering job shape) and ADR-028 §3 with the V-12/V-13 outcomes |
| Supersedes | — |
| Amended | 2026-09-23, amendment 1 (below): §4 `statefulset` backup footprint bounded — compressed WAL shipped and pruned, daily base backup, drill fetches WAL from the base's start segment |

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
   | `local` | MinIO 1 in the chart (`objectstore.local.enabled`), bucket created `--with-lock`, versioning on | MinIO 2 in the chart, plain bucket | Object Lock on A; B is a copy target |
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

## Verification refs

`00-assumptions.md` §5: 2026-09-22 · V-12 · CONFIRMED; 2026-09-22 · V-13 · CONFIRMED;
2026-09-19 · V-6 · CONFIRMED (reference record); 2026-09-19 · V-10 · CONFIRMED (no managed
Postgres; `statefulset` is the mode the drill exercises first).
