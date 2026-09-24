# Plan — Phase 12: the local profile's object stores after MinIO

| | |
|---|---|
| Goal | Restore the clean-clone gate (`make local-down && make local-up && make smoke-test` on a machine that has never seen the repository): replace the two MinIO StatefulSets and the `mc` bucket-init job of the `local` profile with an S3-compatible server whose images are published and which implements what the profile relies on — SigV4 path-style, versioning, bucket Object Lock with per-object COMPLIANCE retention on PUT, ListObjectsV2, HEAD with storage class, rclone `copy --immutable`. Same semantics as the demo's stores (ADR-036 §1), nothing else changes. |
| Inputs | `docs/07` §8.3 (the finding: MinIO's community images withdrawn, repository archived), ADR-036 §1–§3 (per-profile stores, replication), ADR-032 (the platform's own S3 client), ADR-021 §3 (the storage probe), `05` C-42…C-44 (digests, limits), `deployment/local/values-local.yaml`, `templates/minio.yaml`, `templates/minio-init-job.yaml`, `_rclone.tpl`. |
| Do not | Touch the demo's stores or values. Weaken the store-A control (Object Lock) in the local profile. Add a CLI image (`mc`) back: bucket bootstrap goes through the platform's own client, so one fewer third-party image. Edit `00`, `01`, `02`. |
| Gate | An **empirical probe** of the candidate in Docker before any chart change (12.1); then `make check`, `make helm-lint`, and the real gate: `make local-up && make smoke-test` (+ the Grafana port-forward check Phase 11 owed). |

## Decisions

| # | Decision | Why |
|---|---|---|
| P12-D1 | **Pick by probe, not by README.** A scratch script runs the candidate container on this laptop and exercises, with the AWS CLI, rclone and the platform's own `ObjectStore` client: create-bucket with Object Lock, versioning, PUT with COMPLIANCE retention headers, HEAD returning the lock, DELETE of the locked version refused, ListObjectsV2 paging, `x-amz-storage-class` round trip, `rclone copy --immutable` and `check`. Candidates in order: RustFS 1.0.0 (a MinIO-shaped server: same key layout, single binary, port 9000), versitygw 1.8.0 (posix backend), SeaweedFS. The first that passes every step is the one; the probe output is recorded in `docs/07` §8.4. | The platform writes lock headers on every PUT (ADR-032, V-12); a server that ignores them silently would turn the local profile into a lie. |
| P12-D2 | **Bucket bootstrap through the platform's client.** `energyctl bucket-init` (new verb, `fetch.objectstore` gains `create_bucket(object_lock=…)` and `put_bucket_versioning`) replaces the `mc` job: the init hook runs the platform image, creates bucket A with Object Lock + versioning and bucket B plain, idempotently (`BucketAlreadyOwnedByYou` is fine). | One fewer third-party image; the same signed client the platform trusts; the verb is reusable for a tenant's first deploy. |
| P12-D3 | **Chart shape unchanged.** Two StatefulSets (A and B), the same Services and ports (9000), the same Secret keys (`BRONZE_*` as the server's root credentials), the same PVC sizes; only the image, its args/env and the readiness path change. `objectstore.local.image` is the new server by digest; `mcImage` is removed; `resources.minio` is renamed `resources.objectstore`. | Every other template (rclone aliases, NetworkPolicies, the probe hook, the drills) keeps working untouched. |
| P12-D4 | **ADR-036 amendment 4** records the withdrawal, the probe, the choice and the residual (a young project; the profile is a laptop test bed, not a production store). ADR-032's "verified against MinIO" note gets a dated pointer. | The register of what was verified stays true. |

## Tasks

| # | Task | Acceptance | Commit |
|---|---|---|---|
| 12.1 | Probe script (scratch, not committed) against the candidates; record the passing transcript | every step passes on the chosen server | — (evidence into `docs/07` §8.4 in 12.4) |
| 12.2 | `fetch.objectstore`: `create_bucket`, `put_bucket_versioning`, `bucket_exists`; `energyctl bucket-init`; fake-gateway support; tests | unit tests green; the verb is idempotent | `feat(fetch): bucket bootstrap through the platform's client …` |
| 12.3 | Chart: new server in `objectstore.yaml` (renamed from `minio.yaml`), init hook on the platform image, values and schema, `local-secrets` key names; chart and workload tests | `helm-lint` green; StatefulSet count unchanged; no `mc` image anywhere | `feat(chart): the local profile's object stores are <server> …` |
| 12.4 | ADR-036 amendment 4, ADR-032 pointer, `docs/07` §2 and §8.4, `deployment/local/README.md`, README reproduce block un-annotated, `05` row, roadmap, progress | `make check` green | `docs: Phase 12 …` |
| 12.5 | The gate: `make local-down && make local-up && make smoke-test`; `make rollback-drill`; the Grafana port-forward on kind | all green; recorded in `docs/07` §8.4 | `docs(ops): the clean-clone gate holds again …` |

## Stop conditions

- No candidate passes the lock steps → the local profile documents "versioning without Object Lock" as a local-only deviation (ADR-036 §1 compensating control: `copy --immutable` and never-delete) and says so in the README; the demo's control is unchanged.
- Docker memory too small for the profile plus Grafana → Grafana off in `values-local.yaml`, recorded.
