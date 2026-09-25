# Recommendations, without implementation

These are review suggestions for a later authorized task. The current review does not amend accepted ADRs or start a roadmap phase.

## Resolve the design blockers before Phase 1 code

1. **Define the admission boundary (F04).** A target-only contribution should work for an approved dataset contract; new semantics or source permissions should have a clear human-reviewed path. Publish both paths and test the distinction.
2. **Separate source revision and derivation identity (F05).** Include mapping/parser implementation provenance and define current/as-of selection. Corrected replay must append valid results without destroying audit history.
3. **Specify the durable state transitions (F06).** Identify what survives a database outage, how orphaned raw captures become discoverable, how absent captures trigger backfill and how expired workers are fenced.
4. **Choose valid deployment/security mechanisms (F07–F08).** Make upgrade health checks part of a real failure/rollback flow and define enforceable hostname policy under the tenant constraints.
5. **Reconcile the active agent instructions (F14).** Resolve conflicting fields, examples and resource names through the existing ADR process. Keep historical context out of executable task instructions.

## Demonstrate a narrow complete path before optional breadth

The first useful implementation milestone is one committed target shape, fixture capture, immutable raw storage, mapping, Postgres, query and replay, reached through the intended shared library. The next is a second target added by someone without implementation context. Both should run locally through the same interfaces intended for production. This tests abstractions against real shapes early while preserving the rule that target logic does not own semantics.

An MCP interface can be useful, but the brief grades controlled agent work rather than the existence of an MCP server. The no-runtime-LLM decision should remain. Three deployment profiles, five generic parser families, cold-tier movement, an API and a triage LLM pipeline should each justify their maintenance cost after the basic behavior is demonstrable. There is no time limit in the brief, but unnecessary scope still creates more failure modes.

The statements that the evaluator cannot be asked questions in `00` and ADR-015 do not follow from the supplied assignment; it explicitly invites questions. Recording assumptions was reasonable, but capability/cost constraints of a personally available research cluster should not become supposed evaluator requirements. It is also reasonable to choose a reference environment without asking; state that choice as a choice.

## HA decisions that still need an acceptance contract

These are specification gaps, not allegations of broken deployed infrastructure:

| Decision | What must be explicit |
|---|---|
| Failure domains | Worker, node, scheduler/control plane, database primary, object-store endpoint, zone/site and credential/control-plane dependency; which failures are covered by each profile |
| Postgres availability | Replication/failover/fencing design per mode. A DSN and a StatefulSet alone do not specify HA. Operator presence is not evidence of a working failover deployment |
| Local simulation | State the shared-host failure domain of kind and two MinIO instances. Do not describe these as independent host/site resilience |
| Freshness | A target-specific objective, measurement window, grace/tolerance and error budget; separate source freshness from pipeline lag and make metric ownership visible |
| Capture RPO | When a capture is considered durable, maximum lag to the independent copy, outage backlog bounds and alerts when that bound is breached |
| Storage portability | Exact reader/writer backend for hot and cold storage. rclone transport support alone does not implement an application reader or equal retention/immutability on each backend |
| Tier movement | Copy/verify/publish-location/delete ordering, behavior under retention lock, orphan recovery, and preservation of immutable capture metadata. A separate location index may be preferable to rewriting capture logs |
| Restore | Restore both payloads and capture metadata, rebuild the ledger if necessary, preserve original timestamps, validate representative values and current/as-of views, and measure RPO/RTO |
| Initial installation | Database provisioning, credentials, migrations and hook ordering on a completely empty environment, plus re-run behavior after partial installation |
| Build/deployment | How target manifests/custom parsers enter the immutable image or chart bundle; the current wheel definition includes only `energy_platform` |
| Resource limits | Payload bytes, decompression ratio, XML entities/external references, parser CPU/memory, maximum request window, retries, shared host rate budgets and backfill priority |
| Quarantine | Atomic publication of a document's valid results, retained reason/lineage, and an operator path to review and replay after repair |

Select numeric SLOs as design targets and measure them; do not derive publication guarantees from a few source reads. A 15-minute poll interval is not by itself a 15-minute freshness guarantee.

## Required demonstrations before treating the assignment as complete

| Demonstration | Passing evidence |
|---|---|
| Clean reproduction | Fresh-machine prerequisites, locked tool/image versions, exact commands, successful fixture-to-query run, teardown and repeat run; no personal/cloud/LLM credentials for local mode |
| Target contribution | A held-out approved source/shape added through docs and scaffold, no core edits, hand-checked oracle, ordinary CI collects its tests |
| New-contract escalation | An unsupported source produces a clear admission/ADR request rather than fabricated units, a broadened policy or a false pass |
| Negative agent behavior | Bad path change, direct HTTP, undeclared host, secret, invalid unit/sign, missing fixture/golden and changed gate/oracle rejected by the intended check |
| Retry and replay | Duplicate run yields no duplicate business value; same raw/new parser repairs values; older replay cannot become current; NULL source versions remain idempotent |
| Capture recovery | Worker/DB interruption at every durable boundary, later discovery of raw captures, explicit missing-capture backfill, no stale lease commit |
| Domain invariants | Ordinary/spring/autumn days, native hourly data, negative/zero/null values, SOAP fault, partial publication, unit/header drift and T1/T2 reconciliation |
| HA | Kill the selected worker/node/database component, record freshness impact, automatic recovery and data consistency in the failure domain claimed |
| Upgrade/rollback | Both initial install and upgrade tested; injected bad release fails the health check and returns to the prior usable release; compatible schema and retained Bronze verified |
| Restore | Restore into an empty isolated environment from the independent backup and replay cold data; report elapsed time and observable data loss against targets |

For agentic engineering, include the actual task prompt, supplied context, allowed tools, changed paths, gate outputs and where human review was needed. A self-reported successful agent session is weaker than a replayable transcript plus deterministic checks. Do not invent a human trial: distinguish a real junior participant from an agent following junior-facing instructions.

## Suggested submission shape

Lead the README with the working reproduction command, actual data scope, one architecture/failure-domain diagram and the contributor route. Link evidence for rejected bad contributions and outage/recovery demonstrations. Keep pending terms, unmeasured source latency, simulated failure domains and unsupported extensions explicit. Put optional architecture background behind links.

A compact implementation with these demonstrations would answer the original brief more convincingly than a larger set of accepted decisions without executable evidence.
