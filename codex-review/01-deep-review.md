# Deep review against the original assignment

25 September 2026. Source: `bc87c585ce8a61be2995d0b0b1b283f87c2032a6` and the supplied final report. This is a review, not an implementation change.

## Overall judgment

**This is a substantial, functioning answer to the assignment. I agree with the architectural direction and most of the delivered capabilities. I do not agree with declaring the high-availability and recovery work fully complete.**

The strongest part is the answer to the junior/LLM extension problem: narrow declarative targets, platform-owned semantics, explicit admission, synthetic fixtures, hand-derived expected values, and enforced contribution boundaries. This goes materially beyond asking an agent to follow a style guide. The data pipeline and infrastructure are also implemented, with fresh passing checks and a live processing job observed during this review.

The six findings below concern actual failure handling, scheduling, replay or the evidence used to assert recovery. None requires replacing the platform or adding unrelated product features. Several are relatively contained corrections. Green tests establish a strong baseline; they do not cover the new scenarios reproduced here.

## Assignment assessment

| Requirement | Assessment | Basis and limit |
| --- | --- | --- |
| Lead and constrain junior/LLM contributions | **Delivered for the supported extension model** | Route A confines adapters to their target; Route B escalates missing source admission. Registry, target-surface, fixture/golden, dependency, network and PR checks are executable. Live branch protection requires 12 checks and a reviewer. Human semantic review remains necessary. |
| Add new public-data targets easily | **Delivered within admitted capabilities** | Seven manifests use shared machinery. The documented contributor trials include successful adapter additions, a CLI-only path and a correct admission request. Arbitrary new protocols or contracts still require a platform change, which is an appropriate boundary. |
| Scrape and process intraday energy data | **Delivered** | OTE SOAP/XLSX and ČEPS ingestion, raw retention, mapping, SQL history/current views, recapture and reconciliation exist. Fresh PostgreSQL demo and a real live processing job succeeded. |
| Energy-data correctness | **Strong foundation, with repair/recovery gaps** | Explicit decimals, aware time, DST fixtures, transport ownership, source versions and invalidations are implemented. Independent source-field checks of committed synthetic fixtures passed. R4–R6 affect correction and recovery guarantees. |
| Deployments and infrastructure as code | **Delivered, with bootstrap inputs documented** | Terraform, Helm, local/tenant/own-cluster paths and CI/deploy exist. Fresh chart checks, Terraform validation and six mock tests passed. Existing clean-clone evidence was reviewed; a new full cluster was not created in this review. |
| High availability | **Partially delivered** | Leases, raw-first capture, replication, backups and restore machinery improve resilience. The live single control-plane/database node, missing alert evaluation and defects in scheduling/recovery prevent an unqualified HA conclusion. |

The brief does not set an uptime percentage, recovery-time objective or budget. I therefore do not invent an SLO and declare it breached. I do require that “high availability” distinguish continued or automatic service recovery from having durable copies that an operator can restore.

This concern also follows the project's own [assumption A-6](../docs/00-assumptions.md), line 39: working-hours human support is paired with recovery having no manual step and freshness alerting as the operator interface. The demo's later documented topology compromise needs to be reconciled with that objective.

## What deserves a clear pass

- **Core/target separation is meaningful.** Fetching, date handling, mapping, ledger and storage semantics reside in the platform. The narrow manifest and admission boundary reduce the amount of dangerous code a contributor can introduce. Rejecting an unsupported source is a successful constraint, not failed extensibility.
- **Agent controls are layered.** CLI and MCP share the library; target and PR surfaces are checked; unit-test sockets are disabled; provider content is untrusted; optional model triage uses a closed proposal schema. A model is not required for ordinary ingestion. These are appropriate choices for this brief.
- **The data design is substantial.** Bronze-first persistence, append-only versions and occurrences, fencing, explicit source corrections, invalidations and transport ownership are implemented. The earlier review's findings were not simply copied forward as if their fixes did not exist.
- **Verification is unusually concrete.** All seven targets validated. The independent checker read fixture fields without importing the platform mapping code: 42 positive fixtures, 45,493 native rows counted and 215 expected values/UTC instants checked. Those results support the fixtures; they are not an exhaustive audit of every live value.
- **Deployment is real.** The reviewed HEAD has successful CI and deployment runs. The live cluster was ready and processing. Reproducibility still depends on supplied cloud accounts, credentials, state and documented bootstrap actions, as is normal for this kind of system.

I am not asking for a public dashboard, more countries, ENTSO-E, Kafka, Argo, a runtime LLM, a new web application, cosmetic refactoring or an enterprise-sized cluster. None is necessary to satisfy this assignment.

## Material findings

Priority here means importance to the claimed outcome: **P1** should be resolved before an unqualified HA/completion claim; **P2** is a material bounded defect that should be fixed or explicitly excluded from the guarantee. Neither label implies an observed production data-loss incident.

### R1 — P1: the live deployment is recoverable, but has single-node availability dependencies

**Evidence.** [Demo values](../deployment/tenant/values-demo.yaml), lines 12–18, select a single StatefulSet PostgreSQL instance and pin it to `energy-platform-demo-server`. [The StatefulSet](../deployment/helm/energy-platform/templates/postgres-statefulset.yaml), line 42, fixes replicas at one. [The node module](../deployment/own-cluster/terraform/modules/nodes/hcloud/main.tf), lines 55 and 88–89, creates one server and a configurable number of agents. Fresh [node](evidence/live-nodes.log) and [workload](evidence/live-workloads.log) snapshots confirm one control-plane server, one agent and one PostgreSQL instance.

**Consequence.** Losing that server removes both the database host and the control plane responsible for scheduling subsequent Jobs. An additional worker does not provide database failover or another scheduler. Off-provider raw copies and base/WAL backups help recover data, but do not keep this service available through that failure. The official [K3s embedded-etcd HA documentation](https://docs.k3s.io/datastore/ha-embedded) requires at least three server nodes; the observed agent is not a second server.

**Qualification.** ADR-028 deliberately chose a small demonstration environment. This is a conscious limitation, not evidence of careless infrastructure. CNPG/external-database modes exist, but their presence does not prove an end-to-end HA deployment: the [restore template](../deployment/helm/energy-platform/templates/cronjob-restore-drill.yaml), lines 19–21, expressly rejects its drill for non-StatefulSet modes. No node-loss exercise or fresh total-environment restore was performed here.

**Closure.** Either demonstrate a reproducible configuration with control-plane/database failover and measured interruption/recovery, or obtain explicit acceptance of a recoverable single-primary demo as the assignment's availability boundary. Merely redefining HA in the report does not settle the original requirement. A costly active-active multi-provider design is not required by this finding.

### R2 — P2: successful captures are classified as missing because scheduled time is actually start time

**Evidence.** [The capture CLI](../energy_platform/cli.py), line 339, defaults live `scheduled_for` to `datetime.now(UTC)`. [The CronJob template](../deployment/helm/energy-platform/templates/cronjob-target.yaml), lines 18–19, supplies no scheduled instant. [Gap detection](../energy_platform/runtime/gaps.py), lines 82–92, compares those exact timestamps with cron instants at the scheduled minute.

**Reproduction.** A synthetic job starts at `22:15:25.693263`, successfully captures and processes its fixture. After the tolerance expires, `22:15:00` is classified `missing_capture`; backfill fetches the same content again. [PostgreSQL output](evidence/schedule-probe-postgres.json) records a processed run and a separate missing run for the same logical tick, followed by a second Bronze capture. The same probe reproduced in memory.

The [live process log](evidence/live-process.log) independently contains `scheduled_for: 2026-09-24 23:15:25.693263+00:00`, and the [live gap-log sample](evidence/live-gaps-summary.json) contains exact-minute missing captures. This supports the deployed mechanism; the filtered gap sample is not a complete target-by-target loss audit.

**Consequence.** Gap detection, logical-tick idempotency and backfill effort are wrong under ordinary scheduler delay. This causes avoidable source reads and misleading ledger gaps. It is not proof that successfully captured prices were lost.

**Closure.** Propagate a stable intended schedule identity from Job creation through retries, independently of fetch/start time. Verify delayed starts, retries, cron/timezone boundaries and that a genuinely missed tick is still detected. Blindly rounding a substantially delayed job to its current minute would not solve the whole problem.

### R3 — P1: alert definitions are present, but operational alert delivery is not demonstrated

**Evidence.** [Demo values](../deployment/tenant/values-demo.yaml), lines 53–56, enable the exporter but disable monitoring-operator resources. [The metrics template](../deployment/helm/energy-platform/templates/metrics.yaml), lines 183–223, emits a rules ConfigMap and conditionally emits PodMonitor/PrometheusRule objects. Fresh [workload](evidence/live-workloads.log) and [pod](evidence/live-pods.log) inventories show no Prometheus evaluator, Alertmanager or kube-state-metrics in the cluster. The backup/replication rules in [the alerts template](../deployment/helm/energy-platform/templates/_alerts.tpl) rely on Kubernetes job/cronjob metrics.

**Consequence.** Rule text and a metrics exporter do not evaluate conditions or deliver a notification. Private SQL dashboards do not close this gap. A failed or never-running backup/replication/drill can remain unattended, undermining the claimed recovery protection.

**Qualification.** An external monitoring system could supply this function; none was evidenced by the reviewed deployment/configuration or live inventory. This finding is specifically about the reproduced/live stack and the unsupported report claim, not proof that no operator ever checks it manually.

**Closure.** Wire an evaluator, required metric sources and a notification receiver into the documented environment or a documented external integration. Show a controlled stale/failure condition producing a delivered alert and a recovery notification. This does not require adding CRDs to the core chart.

### R4 — P1: core-code corrections can replay as no-ops because release identity stays constant

**Evidence.** [Package version](../energy_platform/__init__.py), line 7, remains `0.0.1`; its Git history shows no change since the skeleton. [Derivation identity](../energy_platform/store/protocol.py), lines 97–110, uses that value plus the contract, mapping and parser reference. [The generic parser reference](../energy_platform/parse/generic.py), lines 63–65, also uses this constant. [The image build](../deployment/image/Dockerfile), lines 29–35, copies the code without injecting a distinct derivation/build identity. An image digest changing at deployment does not change this database identity.

**Reproduction.** A synthetic core-only correction changes the mapper's result by `1` while leaving the payload and manifest unchanged. Replay under the existing version reports `noop`, inserts zero rows and retains `170.13`. Changing the platform version to `0.0.2` as a control makes the same replay insert the corrected derivation and expose `171.13`. Both backends reproduce it; see [PostgreSQL evidence](evidence/derivation-probe-postgres.json). [The conflict clause](../energy_platform/store/postgres.py), lines 62–70, intentionally preserves the existing observation for an identical version identity.

**Consequence.** A parser/mapping bug fixed in platform code can leave previously stored output unchanged despite a successful replay command. The architecture already provides a correction dimension, but the release process is not maintaining it.

**Qualification.** This is a controlled simulation of a code-only repair. It does not establish that current production prices have the simulated error. A manifest change or an explicit version bump can avoid this particular collision.

**Closure.** Tie derivation identity to an enforced semantic implementation version or immutable relevant code/build identity. Add a release/replay test proving that unchanged input and mapping under corrected implementation produce a new derivation while an identical implementation remains idempotent.

### R5 — P2: fresh restore checks compare shared datasets before all contributing targets are rebuilt

**Evidence.** [Drill fingerprints](../energy_platform/runtime/drill.py), lines 115–129 and 193–216, select observations by dataset and transport, not target lineage. Lines 337–358 rebuild and compare each target sequentially. The committed daily and monthly settlement targets share that dataset and transport.

**Reproduction.** Using their committed ordinary-day and March-month fixtures, live holds 9,204 rows. On an empty scratch store, the first target rebuilds 288 and reports 8,916 missing before the monthly target has been rebuilt. Repeating the same drill against the now-populated scratch store passes. [PostgreSQL evidence](evidence/recovery-probes-postgres.json) and the memory result agree.

**Consequence.** A clean rebuild can be reported as failed even though all required data has been restored by the end of that pass. A warm scratch database can hide the defect. The monthly targets had not yet reached their first scheduled live capture in the snapshot, so this is a reproduced upcoming scenario, not a claim of an observed monthly production failure.

**Closure.** Rebuild the complete comparison cohort before checking it, or scope both sides to correct target/capture lineage, including invalidations and replica bounds. Regression-test an empty store with multiple targets sharing a dataset/transport. Do not treat a second successful warm run as the clean-restore proof.

### R6 — P2: raw-only rebuilding cannot reproduce historical mapping derivations

**Evidence.** [The drill](../energy_platform/runtime/drill.py), lines 148–189, reprocesses raw captures using the currently supplied manifest/derivation. Its fingerprints at lines 93–95 include derivation ID, while the live comparison expects historical stored versions. It does not reconstruct each historical manifest/code combination.

**Reproduction.** Process one fixture, then add an unused `ignore_fields` entry to the manifest and replay. The mapping values are unchanged, but a valid new derivation exists alongside the old one: 384 stored versions. A fresh raw-only rebuild under the current manifest produces 192 and fails because the 192 old-derivation versions are missing. [PostgreSQL evidence](evidence/recovery-probes-postgres.json) confirms the same behavior as memory. The changed manifest also passes [schema and contract validation](evidence/mapping-revision-validation.json).

**Consequence.** Normal target evolution breaks the report's assertion that the complete historical Silver database is reproducible from raw copies alone. This is different from R4: correctly giving a change a new identity does not itself preserve the executable history needed to reconstruct every old identity.

**Qualification.** This does not show a failed physical base/WAL restore, nor incorrect current values in this harmless-mapping example. Physical backups can preserve historical derivations. The defect concerns the raw-only full-history guarantee and its checker.

**Closure.** Retain and select sufficient historical manifests, contracts and implementation artifacts to reproduce the promised history, or narrow raw rebuild to an explicitly defined current-data guarantee and rely on physical backup for historical audit recovery. Test both ordinary manifest evolution and platform-version evolution against that stated guarantee.

## Acceptance recommendation

Accept the platform's ingestion, contributor model and IaC work as delivered. Address the false scheduling and release-identity behavior; demonstrate actual alert delivery; correct the two raw-rebuild comparison/history gaps. Then settle and test the availability boundary for the deployed environment.

These are finite acceptance items, not an invitation to keep redesigning the system. The supplied final report should be revised to match the resulting guarantees and observed evidence. The [claim assessment](02-final-report-assessment.md) provides the specific corrections without editing the original.
