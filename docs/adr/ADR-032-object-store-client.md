# ADR-032 — Object-store client for the Bronze S3 backend

| | |
|---|---|
| Status | ACCEPTED — Option B (2026-09-20, author's decision); implementation is the first task of the next session |
| Date | 2026-09-20 |
| Resolves | amends ADR-019 (dependency allowlist) and ADR-027 §3 (outbound HTTP only in `fetch/`) for the Bronze S3 backend of `03` Phase 2 |
| Supersedes | — |

## Context

`03` Phase 2 lists a Bronze "S3 backend (MinIO locally)" next to the in-memory backend. ADR-019's
allowlist names no S3 client, and ADR-027 §3 bans `httpx` and every other HTTP path outside
`energy_platform/fetch/`. The Phase 2 plan (P2-D4) therefore ships the `BlobStore` /
`CaptureLog` protocols with memory and filesystem backends and the hot → cold read path, and
leaves the S3 backend to this decision. Phase 5 (`local-up` with MinIO ×2, Hetzner/OCI stores,
`rclone` replication and tiering) is where the backend is first exercised for real.

## Decision

**Option B is adopted** (2026-09-20). Option A is kept below as the rejected alternative with its reasoning.

**Option A — `boto3`** (plus `botocore`, `s3transfer`, `jmespath`, `python-dateutil`, `urllib3`
transitively) as a runtime dependency, used only inside `energy_platform/bronze/s3.py`; the
egress ban gains a per-file exception for that module, documented in ADR-027 §3 as a second
named egress site ("object store, not sources").

**Option B — a minimal SigV4 client over `httpx`** living in `energy_platform/fetch/objectstore.py`
(so the single-egress rule stays literally true), ~200 lines: `PUT`/`GET`/`HEAD`/`LIST` with
`x-amz-content-sha256`, versioned endpoints, object-lock headers. No new package.

Why B: it adds no dependency, keeps A-7 exact, and the five verbs the
platform needs are small; `boto3`'s value (pagination helpers, retries, credential chain) is
partly provided by `fetch/` already and partly not needed (credentials come from the chart's
`Secret`, one endpoint per store).

## Rationale

Either option is defensible; what is not defensible is deciding it inside a task PR (CLAUDE.md:
no dependency without an ADR; ADR-006: dependency changes are their own gate).

## Rejected

- `minio` SDK (a second HTTP stack, `urllib3`, less common than `boto3`).
- `aiobotocore`/`aioboto3` (async for no reason; the capture path is one request).
- Shelling out to `rclone` from the platform (`subprocess` is banned, ADR-027 §3; `rclone` stays a
  Job image for replication and tiering, ADR-021).

## Consequences

- If A: `deps-allowlist.txt` gains the `boto3` closure; ADR-027 §3 amended; Phase 5 adds a
  `botocore` stub decision under ADR-029.
- If B: `energy_platform/fetch/objectstore.py` with offline tests against a recorded MinIO
  exchange; the local profile's MinIO ×2 (Phase 5) is the first live use.
- Either way the `Bronze` facade, the capture-log layout and the fixtures do not change: the
  backend is behind the protocol shipped in Phase 2.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-6 · CONFIRMED (S3 API with versioning and object lock on
the reference store; the client must send object-lock headers).
