# Assignment assessment and coherence

## Assessment method

The user's original task is the acceptance baseline: build an HA system for public intraday energy scraping and processing, include deployments and IaC so another person can reproduce it, and make adding scrapers easy while constraining bad engineering by juniors and agents. Later ADRs explain implementation choices; they do not by themselves prove the original requirement fulfilled.

The review separates **documented design**, **implemented behavior**, **fresh local verification**, **read-only live observations**, and **unverified operational claims**. A declared limitation is not presented as a concealed defect. A documented exception can nevertheless leave an assignment requirement unmet.

## 1. Agentic engineering

This is the strongest differentiating part of the project. Targets declare source syntax while the platform owns fetch, decode, mapping, persistence and deployment. Dataset, metric, unit and host registries prevent a target author from inventing semantics to make a test pass. The Route A / Route B split makes refusal a legitimate outcome and reserves source admission for maintainers. The same core is used by CLI, MCP and CI. Golden values and Bronze hashes are meaningful constraints, with tests designed to reject undesirable behavior.

GitHub currently enforces one approving review, code-owner review, dismissed stale approvals, up-to-date branches, conversation resolution and 12 required checks. Administrators are exempt; the repository states this accurately. An agent using the owner's login is therefore procedurally restricted, not technically unable to merge or push. The read-only permission in this review was respected; it should not be confused with the application's own sandbox enforcement.

The admission/target PR records are real: see `evidence/github-prs.json` and the linked acceptance report. The observed blind additions demonstrate the supported declarative path. The strictest trial adds another settlement version in an already represented source family. It does not establish arbitrary unfamiliar-source support, a custom parser loader, or an end-to-end shell-free admission workflow. Those are the fair limits of the claim.

AE-01–04 are smaller than the data-recovery blockers, but matter to the requested junior experience: a supposedly green bundle can omit failing tests, the primary bundle-apply instructions collide with a dirty checkout, and constrained MCP gives an unavailable Route B command. The false-negative triage cases also show why model-output safety and useful model input are separate requirements.

## 2. Data engineering

The major abstractions fit the problem: immutable raw captures, independently rebuildable Silver, distinct provider and derivation versions, aware timestamps, exact Decimal values, a run ledger and append-only observations. The platform correctly keeps an LLM outage off the capture/process path. The dataset volume does not demand a streaming broker or multiple orchestration systems; PostgreSQL plus CronJobs is a defensible choice.

The central weakness is composition. Individually plausible mechanisms do not yet form all the advertised end-to-end invariants. Reconciliation creates missing runs but does not advance a processed run to its newer raw correction. Recapture changes the payload pointer without invalidating the active processor's fence. Replay eligibility ignores claimed-but-expired replay attempts. Content deduplication also removes information needed to order a later return to an older payload. These are not style issues: they change which observation a consumer receives after normal operational events.

The live system is delivering rows. In the sampled transaction there were 108,872 historical rows: 12,798 ČEPS SOAP, 1,536 day-ahead SOAP, 11,018 intraday SOAP, 82,656 intraday XLSX and 864 daily imbalance-settlement rows. These are versioned metric rows, not distinct delivery periods. The report does not use the large row total as proof of completeness.

The successful restore implementation deserves credit, but its `live ⊆ rebuild` rule cannot distinguish legitimate extra pending data from deliberately invalidated data. The repository's known T2 deletion is not a durable input to reconstruction. A correct recovery story needs both preserved evidence and preserved decisions about which evidence must not become accepted output.

## 3. Deployment, infrastructure and operations

The local, tenant and own-cluster split is sensible. Digest pins, Helm lifecycle hooks, migration downgrades, restricted pod settings, namespace-scoped OIDC and independent object storage are substantial implemented work. Tests and Make-based CI are reproducible on this machine; the clean-OS/full-cluster run remains prior recorded evidence, not a fresh result from this audit.

The live demo uses one k3s server and one worker. PostgreSQL is a single instance pinned to the server's volume. Failure of that server removes both scheduling and database access. Existing worker processes may finish some work, but there is no second scheduler/control plane or automatic database promotion. K3s distinguishes this from its HA topology; embedded-etcd HA uses at least three server nodes ([official architecture](https://docs.k3s.io/architecture), [embedded-etcd HA](https://docs.k3s.io/datastore/ha-embedded)). This is an expressly accepted cost-saving demo choice, yet the original HA requirement remains only partly demonstrated.

Hourly independent replication and the incomplete CNPG/external recovery modes further limit the production claim. The live exporter and rule files are present, but this cluster has no Prometheus/Alertmanager pods in the observed inventory. External monitoring could exist; no active scraper or notification receiver was verified. Metrics availability is not evidence that an operator will be notified during an outage.

## 4. Energy-domain correctness

The fixture coverage is unusually thoughtful for a take-home: 23/25-hour days, source-native hourly resolution, negative and zero prices, absent values, SOAP faults, incomplete days, decimal syntax and settlement versions. An independent script derived expected samples directly from native XML/XLSX using standard time/decimal handling, without importing platform code or its manifest mapping engine. All 215 sampled golden values and UTC instants matched across 42 positive fixtures; independently derived metric-row counts also matched. This is evidence about synthetic fixtures, not a guarantee that providers always follow those assumptions.

The major domain defect is ownership: the source contract calls T1 SOAP authoritative for `price_vwap` and `volume_total`, but storage chooses the latest capture across both transports. Fresh live SQL found 288 current XLSX rows and 96 SOAP rows for each of those metrics. It is not merely a disagreement in the documentation: the implemented selection contradicts the declared dataset meaning.

Freshness also needs source-specific delivery expectations. Daily, next-day and monthly final settlements cannot all be judged as today's 96 quarter-hours. For the two monthly targets, a same-dataset version-0 row currently supplies their newest-delivery timestamp despite no target capture. The one-week publication-latency campaign was explicitly not run; the report does not invent a publication SLA from the short observation window.

OTE reuse correspondence is recorded as allowing internal use and refusing redistribution; committed fixtures remain synthetic. ČEPS permission/label semantics include recorded limitations. This audit did not contact providers or treat repository correspondence as an independent legal clearance. The technical output is unsuitable for an unqualified external data-distribution claim without settling those recorded conditions.

## Coherence verdict

The architecture is broadly coherent and implemented. The remaining inconsistencies cluster around guarantees and completion claims rather than an absence of software:

- The registry specifies source ownership that the current view does not enforce (DC-03).
- The durable capture and fencing promises do not hold for all correction/replay interleavings (DC-01, DC-02, DC-05, DC-06).
- The restore can be green while reproducing previously invalidated data (DC-07).
- Target-labeled freshness is computed from shared historical dataset/transport rows (DC-08).
- The HA and independent-copy objectives exceed the demonstrated topology and schedule (DEP-01 and the topology limitation).
- The CNPG/external modes are selectable but do not have the documented backup/restore implementation (DEP-02).
- README calls the system complete while explicitly deferring custom-parser execution and actual LLM integration. Those deferrals should remain visible and be tied to an accurately bounded completion statement.

There are also two concrete editorial discrepancies to correct after the behavioral issues: README's T2 incident still says 672 rows await an owner decision, whereas `docs/07-operations.md` and live aggregate SQL show the later 6,048-version removal; the operations report labels the full rebuild approximately 13 minutes although its fresh-schema phase is 1,216 seconds, about 20.3 minutes. The full two-stage job took roughly 34 minutes. None of these is a measured full infrastructure-loss RTO.

Many Phase 0 criticisms have been materially addressed: target test collection, broader egress bans, lock consistency, downgrade checks, release-hook ordering, manifests/admission, executable tooling and real deployments. This report does not carry those old findings forward without current evidence. The next review should concentrate on the new counterexamples and measurable HA acceptance, not restart the architecture from scratch.
