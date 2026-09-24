# Deployment, operations and HA review — 2026-09-24

Reviewed source: `1701ac77175113d744abaad0514489711ed2b1d4`. This is a read-only source and local-render audit. No cluster was created, no image built, no Terraform initialization or plan run, no remote command executed, and no secret read. Current cloud/GitHub observations were gathered independently by the main reviewer; the specific adopted observations are identified below.

**Verdict:** substantial, credible deployment and recovery engineering for the documented demo. The implementation is much stronger than a collection of manifests: release hooks, source-independent processing, immutable raw storage, WAL shipping, independent replication, restore exercises and constrained CI identities are present. It does **not yet establish production high availability**. The demo's single control-plane/database failure point is explicitly accepted; additional implementation defects affect the advertised alternate database modes, network boundaries and recovery objectives.

## Evidence and verification boundary

| Check performed in this review | Result | What it establishes |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/harness/test_chart.py tests/harness/test_workloads.py tests/harness/test_restricted_pss.py -m 'not live' -p no:cacheprovider --basetemp=/tmp/ep-deployment-audit-pytest` | **47 passed in 7.99 s** | Existing chart, workload and restricted-PSS assertions; no live CNI/operator behavior |
| Helm `v4.3.0+gbec5b06`, tenant/demo/all-flags CNPG/external renders | **51 / 51 / 50 / 44 resources**, all exit 0 | Actual rendered output, including alternate-mode defects below |
| Injected connector that always refuses metadata, without a CNI-readiness signal | Gate returned success after **2 attempts / 0.25 s** | Unreachability alone is accepted as policy readiness; no live network was used |
| Source inspection | Make, CI workflows, image, Helm, both Terraform roots and modules, cloud-init, OIDC/RBAC, operations/ADR claims | Implementation and configuration reasoning |

Supporting evidence is in `evidence/deployment/static-probe-summary.json` and `evidence/deployment/{tenant,demo,cnpg,external}-render.yaml`. The JSON records exact render arguments. Image digest was the render-only zero digest; the demo replica endpoint was `https://audit.example.invalid`. These files contain references to Kubernetes Secret keys, not credentials.

Existing green tests correctly establish the assertions they contain. They do not establish valid operator admission, working backups in every mode, effective combined network policies, or recovery within a failure-domain-specific RPO.

## Findings

### DEP-01 — P1: Hourly independent replication does not meet the stated RPO for loss of store A

**Source:** `deployment/tenant/values-demo.yaml:35-44`; `deployment/helm/energy-platform/values.yaml:78-84`; `deployment/helm/energy-platform/templates/cronjob-replicate.yaml:12-14`; `docs/02-architecture-decisions.md:168-176`; `docs/adr/ADR-036-object-stores-and-backups-per-profile.md:153-154`.

**Trigger:** the Hetzner account/site or store A becomes unavailable just before the next hourly `:17` replica run. Captures and WAL written since the previous replication exist only in A. The chart's 10-minute WAL shipment protects a database-node loss **while A remains available**; it does not put those objects in B.

**Impact:** the independent copy may be nearly an hour behind, plus copy time, while ADR-002 states Bronze RPO at most the source polling interval and Silver RPO at most 15 minutes. WAL may lag B further according to when it first reached A. A successful daily restore drill proves recoverability of the replicated history, not these RPO bounds. The checked demo has 15-minute committed capture schedules.

**Recommendation/acceptance:** state RPO separately for database-node loss, hot-store/provider loss and complete cluster loss. Either shorten replication sufficiently and monitor the age of the newest confirmed replica capture/WAL, or explicitly amend the cross-provider target. At acceptance, simulate A unavailable in an isolated drill and measure the newest recoverable source capture and transaction from B, including schedule/copy delay; verify the actual promised bound. Do not infer RPO from CronJob cadence alone.

**Confidence:** high, rendered schedule and data-flow mismatch. No assertion that a real provider loss occurred.

### DEP-02 — P1: CNPG/external are rendered options, but their recovery paths are not implemented as documented

**Source:** `deployment/own-cluster/values-own-cluster.yaml:5-13`; `deployment/helm/energy-platform/templates/postgres-cnpg.yaml:14-30`; `deployment/helm/energy-platform/templates/cronjob-pg-backup.yaml:11`; `deployment/helm/energy-platform/templates/cronjob-restore-drill.yaml:19-38,147-157`; `deployment/helm/energy-platform/templates/_helpers.tpl:128-139`; `docs/adr/ADR-036-object-stores-and-backups-per-profile.md:66-69,87-90`.

**Trigger:** use the documented own-cluster values (`postgres.mode=cnpg`), or change tenant mode to `external` while retaining the enabled restore drill.

**Evidence/impact:** the CNPG render contains one `Cluster`, no backup configuration or plugin, and no `Backup`, `ScheduledBackup` or object-store resource. The platform's `pg-backup`/`pg-wal-ship` jobs render only for StatefulSet mode. Nevertheless the drill still searches B for the custom `<system-id>/base/<timestamp>` layout and builds its local scratch DSN using `$POSTGRES_PASSWORD`. The CNPG/external environment helper does not supply that variable; there is no value for the operator-provided scratch database described in the ADR. A fresh CNPG installation therefore has no chart-configured backup chain for this drill to restore. An externally managed backup chain cannot be selected through the rendered drill contract.

There is a further CNPG admission concern: the generated `imageName` is `docker.io/library/postgres@sha256:…`, with no PostgreSQL version tag and no `imageCatalogRef`. The documented CNPG 1.28 contract obtains its major version from a catalog or version-bearing image tag. This render does not satisfy that documented contract; operator admission was not executed here. See [CloudNativePG image requirements](https://cloudnative-pg.io/docs/1.28/container_images/#image-tag-requirements).

**Recommendation/acceptance:** implement and test each supported mode end to end, or reject/label unsupported combinations at render time. CNPG acceptance must include actual operator admission, healthy primary/standby, a backup object, archived WAL and restore into an isolated CNPG cluster. External acceptance must take an explicit operator-provided scratch DSN and exercise that provider's restore path. Preserve digest pinning while supplying CNPG's major-version information. This is a mismatch with an accepted ADR, not a criticism that operators are intentionally optional.

**Confidence:** high for absent backup wiring and incompatible drill assumptions; documented incompatibility for image version detection, awaiting operator validation.

### DEP-03 — P2: Enabling the Cilium FQDN option leaves public TCP 443 allowed

**Source:** `deployment/helm/energy-platform/templates/ciliumnetworkpolicy.yaml:7-32`; `deployment/helm/energy-platform/templates/networkpolicy.yaml:183-209`; `tests/harness/test_chart.py:175-180`.

**Trigger:** set `egress.fqdnPolicy=cilium`, as the all-flags render does, and rely on it to constrain direct capture-pod egress to the declared names.

**Impact:** the Cilium allowlist is added alongside the unconditional standard NetworkPolicy permitting public `0.0.0.0/0` on TCP 443 for the same roles. Cilium allow rules combine as a union, so the broader rule still permits other public HTTPS destinations. The application host registry remains useful; the optional network layer adds no effective host restriction here. This follows the rendered policies and [Cilium's rule semantics](https://docs.cilium.io/en/stable/security/policy/intro/#rule-basics), rather than a live packet probe.

**Recommendation/acceptance:** make the broad public rule conditional on `fqdnPolicy=none` and implement the complete Cilium DNS/FQDN path. In an isolated Cilium test, prove a registered source and object store remain reachable, an unrelated public HTTPS host is blocked by direct transport, and private/metadata addresses remain blocked. Merely counting a `CiliumNetworkPolicy` object is insufficient.

**Confidence:** high, rendered objects plus authoritative policy semantics.

### DEP-04 — P2: An omitted external-Postgres CIDR list opens that port to every destination

**Source:** `deployment/helm/energy-platform/templates/networkpolicy.yaml:68-76`; `deployment/helm/energy-platform/values.yaml:135-137`; `deployment/helm/energy-platform/values.schema.json:94-97`.

**Trigger:** change only `postgres.mode=external`; leave the default `egress.postgres.cidrs: []`.

**Evidence:** the successful external render contains `egress: [{to: null, ports: [{protocol: TCP, port: 5432}]}]` for all platform verb roles. The schema does not require a non-empty external database destination list.

**Impact:** a missing configuration fails open: the rule allows TCP 5432 to arbitrary public/private destinations, rather than only the intended database. Kubernetes defines an empty destination list as all destinations. See the [NetworkPolicy API reference](https://kubernetes.io/docs/reference/kubernetes-api/networking/network-policy-v1/). This weakens the process-pod isolation boundary when the external mode is selected.

**Recommendation/acceptance:** refuse external mode without at least one valid destination CIDR or another explicitly constrained selector. The empty case must fail Helm rendering; a configured case must allow only its declared destinations. Confirm with both render assertions and isolated packet tests.

**Confidence:** high, reproduced render and API semantics. The deployed demo uses StatefulSet mode, so this finding does not claim its current database rule is open.

### DEP-05 — P2: The metadata canary cannot establish CNI readiness after the independent node block

**Source:** `energy_platform/fetch/policy_gate.py:41-64`; `deployment/own-cluster/node-metadata-block.sh:24-25,46`; `deployment/helm/energy-platform/templates/_helpers.tpl:203-216`; `docs/07-operations.md:61-89`.

**Trigger:** the node metadata DROP is active (as the runbook records), and a new pod starts while kube-router has not yet installed that pod's policy. The metadata destination is already denied by the node rule regardless of the pod's NetworkPolicy.

**Impact:** two failed connects are treated as proof of readiness, but can equally mean an independent firewall, absent metadata route, or unavailable endpoint. The deterministic probe succeeded after two independent refusals without any readiness signal. The node block improves metadata security; it also removes the canary's ability to tell whether **other** egress restrictions are installed. The observed init-container delay may happen to be enough on the demo, but it is not a fail-closed CNI synchronization mechanism. A live egress bypass after the node change was **not** tested here.

**Recommendation/acceptance:** use an actual policy-ready signal/CNI guarantee, or a reachable controlled canary whose denial specifically depends on the per-pod policy; describe any residual timing assumption accurately. Re-run first-packet process-to-public and private-destination tests after the node block, including deliberately delayed policy programming. Unit coverage should include an independently unreachable metadata endpoint.

**Confidence:** high for the logical limitation; operational exploitability unverified.

## Strengths that deserve credit

- Digest-pinned runtime/base/third-party images, pinned GitHub checkout actions, provider lockfiles, locked Python dependencies and explicit resource limits are enforced by tests. The mutable apt repository and k3s installation script still prevent a claim of bit-for-bit rebuild reproducibility; the deployed image digest itself is immutable.
- Helm's smoke is an actual `post-install,post-upgrade,test` hook; migration ordering distinguishes first install from upgrade. The Make targets use atomic rollback/wait semantics for Helm 3 and 4. The smoke uses fixture data in a scratch schema and scratch Bronze rather than contaminating production tables. The rollback drill is scheduled in CI.
- StatefulSet backup work uses compressed WAL, bounded shipping, a daily base and a Postgres system identifier in the archive path. Replication uses `copy --immutable`, not deletion-propagating sync. The restore workload reads B and performs both database restore and Bronze reconstruction.
- Namespace-scoped deployment RBAC has no direct Secret/exec/port-forward permissions; Helm uses ConfigMaps for release storage. OIDC is restricted by repository, branch and workflow; build and deploy permissions are separated. Creating workloads still confers indirect access to namespace secrets, which ADR-035 explicitly acknowledges. Authentication/branch-protection settings need independent live verification.
- Core tenant rendering requires no CRD-backed kind. Pods use non-root identities, read-only root filesystems, dropped capabilities, seccomp, and disabled service-account token automount. Public-source fetching is separated from processing at both workload and network-policy levels.
- The operations log records unsuccessful drills and real first-deploy defects, rather than presenting mock-provider plans as live success. Local reproduction and demo configuration have clear, distinct roles.

## Original-brief acceptance and limits

| Area | Fair assessment |
|---|---|
| Reproducible demo deployment | Strong source implementation with recorded clean-clone runs. This review only re-ran render/static tests, not a clean build or cluster bring-up. |
| High availability | The main reviewer's `evidence/live-nodes.json` and `evidence/live-workloads.json` confirm the demo uses one k3s server plus one agent and one Postgres StatefulSet pinned to the server. Losing it stops scheduling/database access; there is no automatic database failover. ADR-028 expressly accepts demo control-plane non-HA. This is an honest scope limit, but a production HA acceptance criterion remains unmet. |
| Production own-cluster profile | Terraform exposes one server plus agents; increasing agent count does not add a control plane. CNPG replication is an optional intended path with the implementation gaps in DEP-02. No node/DB failover was verified here. |
| Disaster recovery | Extensive mechanisms and recorded success, but RPO needs DEP-01's failure-domain correction and actual-age monitoring. A warm scratch drill does not measure replacement infrastructure, recovery of identities/secrets, traffic/scheduler resumption and end-to-end outage RTO. |
| Monitoring | Exporter, query/rule ConfigMaps, dashboard and optional operator objects are implemented. The main reviewer's cluster-wide inventory (`evidence/live-all_workload_names.txt`) shows the exporter but no Prometheus/Alertmanager pods; the demo disables operator objects. An external scraper/receiver is not established by that inventory. Active paging is unverified. |
| OpenStack portability | Terraform root and mock tests exist; it is deliberately never applied. Swift storage provisioning and the S3-only rclone helper (`deployment/helm/energy-platform/templates/_rclone.tpl:6-16`) need an explicit compatible endpoint/adapter verification before treating the reference replica path as operational. The broad virtio volume glob also requires actual-device verification. These are portability limits, not failed live tests. |
| Infrastructure reconstruction | Some live hardening remains an operator procedure: the metadata block is not part of cloud-init, and the runbook records an out-of-band firewall CIDR correction. New-node acceptance must reapply those steps. Local Terraform state backup is manual. This is not a fully declarative reconstruction of current operational state. |
| Cold tier | `mode=move` is explicitly unexercised against a real cold store in README:139. Do not count it as production-verified; do not call this disclosed deferral a hidden defect. |

Two further acceptance checks are warranted, without treating untested failure scenarios as demonstrated live defects:

- **Subsequent boots without the data volume:** `deployment/own-cluster/terraform/cloud-init/k3s-server.yaml.tftpl:46-59` writes `nofail` in fstab and asserts `mountpoint` only during first boot. No persistent k3s mount requirement is provided by the checked source. Verify a later restart cannot start against an empty/wrong local-path directory when the device is unavailable.
- **Backup failure and age notifications:** the shipped `deployment/helm/energy-platform/templates/_alerts.tpl:52-65` covers failed restore/replication Jobs but not `pg-backup`, `pg-wal-ship` or backup age. Prove the monitoring integration detects failed/missing WAL shipment while ingestion and replication remain healthy, before the RPO is exceeded. A job that never ran has no failed-Job metric.

Runbook precision also needs correction before submission: `docs/07-operations.md:417-427` records 777 seconds for restored-database reconciliation and 1,216 seconds for the fresh Bronze reconstruction, then calls the full rebuild about 13 minutes. The second measurement is about 20.3 minutes; the whole two-stage job spans about 34 minutes. Report those separately, with the tested data size, and do not present either as measured infrastructure recovery time.

The shortest credible production acceptance path is: fix the rendered mode/policy defects, agree failure-domain-specific RPO/RTO, then exercise node/database failover and B-only disaster recovery with a proven alert receiver. That work is distinct from the strong, already implemented junior/agent extension harness.
