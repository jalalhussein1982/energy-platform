# ADR-036 — Object stores per profile, Bronze replication, and Postgres backups without a custom image

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-22 |
| Resolves | D-3 (`02-architecture-decisions.md` §4.2); amends ADR-002 "pgBackRest/WAL-G with PITR" (tooling, not the guarantee); refines ADR-021 §1 (tiering job shape) and ADR-028 §3 with the V-12/V-13 outcomes |
| Supersedes | — |

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

## Verification refs

`00-assumptions.md` §5: 2026-09-22 · V-12 · CONFIRMED; 2026-09-22 · V-13 · CONFIRMED;
2026-09-19 · V-6 · CONFIRMED (reference record); 2026-09-19 · V-10 · CONFIRMED (no managed
Postgres; `statefulset` is the mode the drill exercises first).
