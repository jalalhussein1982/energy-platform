# Independent delivery and claim challenge

Reviewed 2026-09-25. Read-only review of source and the already-collected evidence under `codex-review/evidence/`. Baseline evidence identifies commit `bc87c585ce8a61be2995d0b0b1b283f87c2032a6`. No new live reads, infrastructure actions, fault injections, source edits, or commits were performed by this reviewer. This file is the only artifact written. Detailed recovery/derivation probes belong to the other review streams and are deliberately not duplicated here.

## Verdict against the brief

**Substantial delivery, with a real live ingestion system, credible reproducibility, and unusually concrete contributor controls. The unqualified claim that the brief's high-availability requirement has been delivered is stronger than the evidence.**

It would be unfair to call this a skeleton, dismiss its architecture because it is inexpensive, or require a public API, large cluster, live LLM service, Kafka, Argo, TimescaleDB, ENTSO-E, or enterprise operations suite. The brief permits the data and environment to be chosen. The declarative adapter path directly addresses its junior/agent requirement. A batch ingestion system can sensibly prioritise durable capture, recovery and bounded freshness over continuous query availability.

It is nevertheless fair to require the final report to distinguish those properties from automatic continuity after the loss of the only database/control-plane node. The brief explicitly says high availability; the project's own assumption A-6 says recovery has no manual step (`docs/00-assumptions.md:39`), and its own architecture sets recovery targets (`docs/02-architecture-decisions.md:168-179`). The demo's documented acceptance of an outage is a qualification of the demonstration, not independent evidence that the original requirement is satisfied.

Recommended acceptance wording: **“The core ingestion and constrained target-contribution goals are substantially delivered. Deployment and recovery mechanisms are implemented and partly exercised. Automatic high availability and operational alerting are not demonstrated by this live demo; the final report needs to state that limitation.”** Further correctness findings from the independent recovery probes may justify a stricter operational acceptance verdict.

## Material issues and necessary qualifications

### 1. The live topology demonstrates a recoverable demo, not automatic HA

- `deployment/tenant/values-demo.yaml:12-18` selects a StatefulSet, local-path storage, and pins PostgreSQL to `energy-platform-demo-server` because that is the only node with its data volume.
- `deployment/helm/energy-platform/templates/postgres-statefulset.yaml:40-59` hardcodes one replica and applies that node selector.
- `deployment/own-cluster/terraform/modules/nodes/hcloud/main.tf:55-89` creates one server resource; only agents have a count. This is not presently a topology that adds control-plane redundancy by merely increasing the worker count.
- `codex-review/evidence/live-nodes.log` shows one control-plane server and one agent. `live-workloads.log` shows PostgreSQL `1/1`.
- ADR-028:77 and ADR-035:113-115 explicitly accept this single control-plane point of failure. This is a disclosed scope/cost choice, not a discovery of a concealed architectural defect.
- The alternate CNPG template exists (`templates/postgres-cnpg.yaml:7-22`), but it is not the live demo. ADR-036:217-230 explicitly says CNPG/external backup and drill wiring is deferred and prevents unsupported drill combinations from rendering. Do not present the alternate flag as proof of a completed, tested HA deployment path.

**Consequence:** Losing the server leaves no PostgreSQL replica to promote and no replacement control plane represented by this deployment. A live second worker does not solve that. Replicated Bronze and WAL can preserve/recover data, but do not by themselves resume the schedules or replace infrastructure and identities.

**Qualification:** Do not assert a tested outage duration or actual data loss. No server-loss test was performed. Do not inflate this into a demand for a particular commercial cluster architecture. The necessary correction is either acceptance of a clearly named non-HA demonstrator or evidence of the required automatic recovery/failover behaviour.

### 2. Alert rules are implemented; operational alert evaluation and delivery are not demonstrated

- `templates/metrics.yaml:183-192` always emits the alert rules as a ConfigMap when metrics are enabled. `:192-220` creates PodMonitor/PrometheusRule resources only when `metrics.operator.enabled` is true.
- The demo explicitly sets that flag false (`values-demo.yaml:53-56`).
- The supplied all-namespace live workload and pod inventories contain the exporter and Grafana, but no Prometheus, Alertmanager or kube-state-metrics. The Kubernetes `metrics-server` seen in the inventory is a different workload and is not evidence of these alert rules being evaluated.
- `templates/_alerts.tpl:52-88` relies on `kube_job_status_failed` and `kube_cronjob_status_last_successful_time` for restore, replication and backup alerts; the annotations explicitly name kube-state-metrics as a dependency.
- `docs/overview/final-report.md:100` says three rules “watch” the replication, WAL and backup ages. The file/configuration exists; no supplied evidence shows a running evaluator loading it or an alert reaching an operator.

**Consequence:** A stopped backup, broken replication, failed restore drill, or data-quality issue may remain visible only to someone inspecting dashboards/jobs. That matters to the claimed best-effort unattended recovery model, not merely presentation polish.

**Qualification:** `operator.enabled=false` alone does not prove alerting cannot exist: a non-operator/external Prometheus could read the rules and scrape the exporter. None is evidenced here. State **“active alerting not demonstrated”**, rather than claiming universal absence. Preserve full credit for the exporter, useful rule definitions and private dashboards.

### 3. The nightly/full recovery proof is overstated in the final report

- The report repeatedly claims the database is proved rebuildable every night (`final-report.md:9,28,31,57`).
- The supplied live job inventory distinguishes a failed scheduled drill (`energy-platform-restore-drill-29836890`), a failed manual retry, and the successful `restore-drill-manual-3`. The CronJob's recorded last-success time alone should not be reported as an independently successful scheduled nightly run.
- `live-restore-log.txt` genuinely reports successful restored-database and fresh-schema Bronze phases, taking 776.8 and 1216.4 seconds. This is valuable evidence and must not be dismissed.
- The same log expressly excludes runs newer than the replica frontier. It also accepts `live ⊆ rebuild`, with 11,424 extra XLSX versions. It is not evidence of exact equality of every live history row at the current wall-clock time.
- The successful run was 2026-09-24 02:53–03:26 UTC. Its output predates the later invalidation job visible in `live-jobs.log` (20:48–21:18 UTC). It therefore cannot prove recovery of that later repaired state or every change in the final deployed revision.
- `docs/07-operations.md:504-517` already states the correct limitation: around 34 minutes for the two-phase job on warm infrastructure, excluding replacement nodes, identities, secrets and resumed schedules. ADR-036:204-207 repeats that the whole-environment recovery exercise has not been run.

**Consequence:** A single successful recovery run is evidence for the tested state and comparison rules, not a demonstrated nightly service level or a complete infrastructure-loss RTO.

**Recommended wording:** “A nightly restore job is configured. A successful manually launched run on 24 September restored backups and rebuilt Silver from the independent Bronze copy in about 34 minutes on existing infrastructure, subject to the replica-frontier comparison. Full environment recovery has not been timed.” Apply additional limitations from the other reviewers' current recovery probes before making a final acceptance claim.

### 4. The report turns useful agent guardrails into broader guarantees

The contributor design deserves a strong pass. The report should preserve the distinctions its own engineering documents make:

- **Guardrails versus an agent sandbox.** `docs/05-constraint-matrix.md:145-151` and ADR-027:57-60 explicitly state that static checks expose accidental/deliberate bypass; the sandbox is the boundary. `docs/threat-model.md:92-94` says developer-mode sessions hold the owner's authority and Level 3 is procedural outside the sandbox. The final report's “a boundary, not a code review” (`:11`) and broadly impossible-to-express language (`:175`) omit that important distinction. The snapshot of branch protection also has `enforce_admins:false`: required checks/review are real, but not an absolute boundary for the repository owner.
- **The successful blind sessions are bounded evidence.** `docs/09-acceptance-report.md:14-19` records three Route A contributions, two for the same daily settlement source, plus one correct Route B admission request. `:70-72` discloses prior global memory in runs 1–3; only run 4 demonstrates an empty profile, and it had the version-1 sibling target as a worked example (`:107-112,172-181`). `:139-147` records Bash/git/gh use. These runs demonstrate guided developer-mode contribution, not that all participants were confined to the nine MCP tools. This still directly supports the brief's practical “easy target addition” goal.
- **MCP does not itself create remote PRs.** `energy_platform/mcp/tools.py:458-483` writes a bundle and names checks not run. `:371-396` places a Route B request in the outbox. A human or separate CI process opens the PR. `docs/08-adding-a-target.md:241-246` is accurate; `final-report.md:169` compresses this into “open a PR, or file an admission request”.
- **Optional parser execution and a real LLM backend are not delivered.** The current contributor guide refuses custom parsers pending platform work (`docs/08:191-193`); `README.md:165-166` explicitly defers both the live LLM client and parser loader. This is a reasonable boundary for admitted sources served by generic parsers. It is not evidence that arbitrary websites or arbitrary custom scraper code are already supported safely.

**Recommended wording:** “Declarative targets, admission checks, negative tests and required CI reduce common contributor mistakes. Constrained MCP mode additionally narrows the tools available. Developer-mode agents retain their session's authority and require review. Four contribution exercises passed: three adapter additions and one admission request; one adapter run used a strictly empty profile.”

This should normally be one report-confidence qualification, not a collection of extra defects. There is no evidence here to claim all gates are ineffective or that the contribution workflow fails its intended scope.

## Other high-impact wording corrections

1. **RPO is a design bound with assumptions.** `final-report.md:56` says at most 15 minutes for provider/store-A loss. `values-demo.yaml:46-49` and ADR-036:191-196 correctly say **replication interval plus copy time**. Include successful job execution and provider availability as assumptions. This is material because the report is making a failure-domain guarantee, not merely rounding a performance statistic.
2. **Automatic rollback is bounded to detected upgrade failure.** The genuine hook chain and failure rollback should pass. The report's “a bad deploy → nothing” and “untouched” (`:58`) are too broad. ADR-016:19-21 and ADR-025:43-46 explicitly say schema changes are not automatically undone and semantic data corruption is not reversed by Helm. `deployment/local/drills/rollback.sh:6-16,40-74` tests two injected hook failures with schedules suspended and throwaway smoke data. That does not prove automatic rollback of every bad parser, mapping, migration, or error appearing after the upgrade gate. `docs/07:553-581,699-706` documents successful bounded drills; do not discard that evidence.
3. **Review disposition is not uniform verified correction.** “17 of 17 fixed with a reproducing negative test and closed” (`final-report.md:207,216`) should be “review findings addressed by fixes, explicit limitations or deferred capability”. The response table itself says unsupported database modes now refuse the drill, bundle testing remains intentionally limited, and topology is unchanged (`docs/reviews/2026-09-24-codex-review-response.md:241-258`). New probes must decide whether the claimed semantic fixes hold today.
4. **Seven targets is not seven quarter-hourly datasets.** The report's own accurate table (`:74-82`) distinguishes the two intraday transports, ČEPS, daily day-ahead, hourly settlement and monthly versions. Its opening and flow paragraph (`:9,46`) should retain that distinction. Monthly schedules that have not reached their first due date are not failed ingestion merely because the inventory has no successful scheduled capture yet.

## What deserves a genuine pass

| Requirement or capability | Evidence and bounded conclusion |
|---|---|
| Substantial working ingestion implementation | Current `make-check.log`: 928 offline tests pass; all seven manifests validate. Existing live captures/processes, replication, WAL and base-backup jobs have success evidence. This is implemented, running software. |
| Canonical processing and nominal database path | `db-and-demo.log`: 33 PostgreSQL tests pass and the offline database demo succeeds. `independent-fixture-check.json`: 42 positive fixtures, 215 sampled values/UTC instants, 45,493 native rows independently checked with no platform imports. This is much stronger than self-confirming goldens, while still bounded to the selected fixtures/nominal cases. |
| Safe contribution structure | Target-only Route A, admission-only Route B, platform-owned semantics, validation, sockets disabled in unit tests, goldens, and separate registry ownership are coherent mechanisms. The acceptance report records successful practical exercises and independently checked expected values. |
| CI and deployment tooling | Fresh static evidence passes Helm renders/lint under three values sets, workload/digest/resource checks, restricted Pod Security, dependency allowlist and secret scan. Six Terraform mock tests and validation pass across two roots. Supplied GitHub evidence shows CI and deploy success at the baseline commit. These do not replace a clean deployment test, but are real positive evidence. |
| Reproducibility | Terraform modules, chart, Make targets and the detailed clean-clone operations log form a credible reproducible path; latest local rebuild is recorded at `docs/07:699-709`. This review did not recreate the live infrastructure, so call that recorded rather than freshly independently verified end-to-end. |
| Backup/recovery engineering | Independent provider copy, daily base backup, WAL shipment, scheduled drill, successful manual restore and immutable/raw-first design are meaningful DR work. Give credit without converting a tested warm recovery into automatic failover or full-environment recovery proof. |
| Honest architectural scope in lower-level docs | ADR-028 acknowledges demo topology; ADR-036 distinguishes RPO domains and recovery timings; the contributor guide defers unsupported parser execution; the threat model distinguishes procedural authority from the sandbox. The engineering documentation is more candid than the final overview. |

## Findings to drop or downgrade

- Do not flag the lack of public dashboard/API, ENTSO-E, TimescaleDB, Kafka, Argo, live inference, or a second cloud cluster as independent failures of the assignment. None is necessary to meet its stated data/extension scope.
- Do not equate manual creation of operator-held credentials, account setup, or an explicit Terraform apply with non-reproducibility. The requirement is a reproducible environment, not unattended account creation or removal of human authority checks.
- Local Terraform state is a disclosed team-operations improvement; it is not by itself a reason to fail this evaluation deployment.
- Do not count every prior defect again simply because an old probe intentionally models a retired repair. Test the supported path. A fail-closed unsupported configuration is an improvement even when it does not deliver that optional capability.
- Do not report a failed historical job as proof the current nominal pipeline is broken when later successful evidence exists. Report exactly which behaviour, version and state each run exercised.
- Do not attack example counts, stale module numbers or editorial duplication as if they were availability findings. Retain wording corrections only where they change the promised behaviour or strength of proof.

## Submission recommendation

The application and IaC are credible work products and the junior/agent design directly answers the brief. A fair final review should lead with that delivery and then state the acceptance boundary: **working ingestion and contribution demonstrator; recoverability partly exercised; literal automatic HA and active operational alerting not established; recovery correctness subject to the independently reproduced findings.** The overview should be revised to match the narrower, often more accurate ADR and operations evidence before it is used as an assurance statement.
