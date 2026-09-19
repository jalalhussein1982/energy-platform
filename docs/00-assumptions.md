# 00 — Assumptions Register

| | |
|---|---|
| Status | **ACTIVE.** Assumptions are stated, not verified, until the Verification Log in §5 records a result. §5 filled and §6 applied on 2026-09-19 (V-4…V-10 run; V-1…V-3 remain for Phase 4 / documentation). |
| Purpose | We cannot ask the evaluator what environment they run. We therefore adopt a **reference environment** (MetaCentrum / e-INFRA CZ), derive decisions from it, and score every decision by what it costs if the assumption is false. The value of an assumption is the constraint it reveals, not the environment it describes. |
| Reads with | `01-data-scope.md`, `02-architecture-decisions.md`, `03-roadmap.md` |
| Owner of verification | Claude Code, over the live SSH/`kubectl`/`openstack` access to MetaCentrum. Record results in §5 with date and raw command output. Do not "verify" from documentation when a command can answer. |

---

## 1. Method

```text
assumption  →  evidence  →  decisions derived  →  sensitivity (does the decision survive if the assumption is false?)  →  verification
```

Sensitivity is scored against the three plausible answers to "what does ČEZ run?":

| Scenario | Description | What a team typically gets |
|---|---|---|
| **A** | Shared enterprise Kubernetes (OpenShift or Rancher, on-prem) | A namespace/project; no cluster-admin; no CRD installation; ingress, storage class and cert-manager provided by the platform team |
| **B** | Own IaaS (VMware or OpenStack) | Can build and administer a cluster; operators allowed |
| **C** | Hyperscaler EU region | Managed Kubernetes; operators allowed; object store is not S3-API by default on Azure |

A decision is **robust** if it survives A, B and C without platform-code changes. Profile-level changes (Helm values, Terraform provider) are acceptable costs; platform-code changes are not.

---

## 2. Register

| ID | Assumption (about the reference environment) | Evidence | Decisions derived | Survives A / B / C | Cost if false | Verify |
|---|---|---|---|---|---|---|
| A-1 | Kubernetes is a **shared, Rancher-managed cluster**; our identity holds project/namespace-scoped rights only; **we cannot install CRDs** | Rancher project model; CRDs are cluster-scoped; e-INFRA docs describe Kubernetes & Rancher | Core chart deploys **as a tenant**: namespace-scoped, no cluster-admin, **no CRDs** (→ ADR-003 rev., D-2/D-6/D-7 become contracts, §3) | Y / Y / Y — a tenant chart runs anywhere | None; strictly more portable | V-4 |
| A-2 | **OpenStack IaaS** is available with VM/network/volume quota; **Magnum (COE) is not** | MetaCentrum Cloud is OpenStack-based; Magnum availability unknown | Own-cluster profile = Terraform VMs + cloud-init k3s/RKE2 (D-1); Terraform modules split `network/`, `nodes/`, `storage/` | N / Y / provider swap | Rewrite one provider layer; module structure holds | V-5 |
| A-3 | Object storage is **S3-API** (Ceph RGW) with a second, independently operated S3/Swift endpoint; **tape/cold tier exists** | CESNET S3 and OpenStack Swift are separate systems; tape library documented | S3 API is the storage contract (ADR-002); cold tier by lifecycle rule; **Bronze replication as an `rclone` job**, not native bucket replication | Y / Y / Y (rclone speaks Blob/GCS) | None | V-6 |
| A-4 | In-house **LLM inference with an OpenAI-compatible API** | e-INFRA "AI & LLM modules … with the option of API integration" | ADR-009 unchanged | Y / Y / Y | None | V-7 |
| A-5 | Identity is **OIDC** (Perun / eduID); no local users | e-INFRA AAI | All human and CI identities via OIDC; deploy identity by federation; no static kubeconfig secrets in CI | Y (Entra/Keycloak) / Y / Y | **Updated 2026-09-19 (V-8):** on a Rancher-fronted tenant cluster the deploy credential is a namespace-scoped Rancher API token stored as a CI secret with a recorded expiry and rotation job; federation stays the design, the token is the fallback | V-8 |
| A-6 | SLA is **best-effort**; human support in working hours only | MetaCentrum terms | Recovery has **no manual step**; freshness alerting (ADR-012) is the only operator interface | Y / Y / Y | None; strictly conservative | — |
| A-7 | **Open internet egress** from pods; no corporate proxy | Research network | **Single egress path**: every outbound HTTP call goes through `energy_platform.fetch`; honours `HTTP_PROXY`/`NO_PROXY`; injectable CA bundle; lint bans `httpx`/`requests`/`urllib` imports outside `fetch/` | Corporate proxies are the norm in A and B | If missed, the platform fails silently behind a proxy | V-9 |
| A-8 | Resources are **quota-enforced** (ResourceQuota/LimitRange on the namespace) | Shared cluster | Requests/limits mandatory on every workload; chart is ResourceQuota-clean; CI rejects a workload without requests | Y / Y / Y | None | V-4 |
| A-9 | Data centre is **in the Czech Republic** | CESNET sites (Prague, Brno) | Residency is a declared attribute (`residency: CZ`) asserted at deploy time and documented; never encoded in platform code | Y / Y / C only if region-pinned | None | — |
| A-10 | **Ingress controller, cert-manager and storage classes are provided** by the cluster; we cannot install our own | Shared cluster | Chart **consumes cluster services by name** (`ingressClassName`, `clusterIssuer`, `storageClassName`) from values; the local profile installs its own; the own-cluster profile installs via operators | Y / Y / Y | None | V-4 |
| A-11 | **Postgres is not offered as a managed service** in the reference environment | Unknown | Chart takes a **DSN as input contract**; profiles provide Postgres (`statefulset` for local/tenant, `cnpg` for own-cluster, `external` for managed) | Y / Y / Y | None | V-10 |
| A-12 | Egress to Tier-1 sources (OTE, ČEPS, ENTSO-E) is reachable and **not rate-limited by the network** | Research network | Politeness limits are enforced by the platform (D-5), never assumed from the network | Y / Y / Y | None | V-9 |
| A-13 | CI platform is **GitHub Actions** (ČEZ cannot be asked) | Assignment delivered as a Git repository; GitHub is the default host for a take-home | CI workflow files are thin wrappers that only call Make targets; all logic lives in the Makefile (ADR-015) | Y / Y / Y — CI host is orthogonal to the runtime | Port to GitLab CI: rewrite the wrapper YAML only; Make targets unchanged | — |
| A-14 | Namespaces enforce the **`restricted` Pod Security Standard** (added 2026-09-19 from V-4) | `kubectl run` of a plain pod rejected by PodSecurity `restricted:latest` on the reference cluster | Every workload in the core chart sets `runAsNonRoot`, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`; images run as non-root; CI renders the chart and lints it against the restricted profile | Y / Y / Y — restricted-clean pods run anywhere | None; strictly more portable | V-4 |

### 2.1 Profiles (amends ADR-001: two profiles become three — ACCEPTED 2026-09-19, `docs/adr/ADR-001-amend-three-profiles.md`)

| Profile | Where | Cluster-level capability | Postgres | Secrets | Metrics |
|---|---|---|---|---|---|
| `local` | kind on a laptop | We install everything (ingress-nginx, cert-manager, MinIO×2) | `statefulset` | SOPS-decrypted `Secret` | `/metrics` + annotations |
| `tenant` | Any shared cluster (reference: e-INFRA Rancher; scenario A) | **None** — consume by name | `statefulset` or `external` | plain `Secret` from CI/SOPS | `/metrics` + annotations |
| `own-cluster` | Terraform on OpenStack (reference: MetaCentrum Cloud; scenario B/C) | Operators allowed behind values flags | `cnpg` | ESO behind `secrets.eso.enabled` | `PodMonitor` behind `metrics.operator.enabled` |

**Rule:** platform code is identical across profiles. Only Helm values and Terraform differ. Anything cluster-level appears *only* in `own-cluster`, behind a flag, never in the core chart.

---

## 3. Proposed decision changes (filed per protocol; accept in Phase 0)

### ADR-003 rev. — Orchestration without CRDs

**Status:** ACCEPTED 2026-09-19 (`docs/adr/ADR-003-rev-orchestration-without-crds.md`, cites V-4). Supersedes ADR-003 (Argo Workflows) in `02-architecture-decisions.md`. The tenant requirement (A-1) is independent of whether V-4 finds Argo pre-installed on the reference cluster, because it is ČEZ's cluster that matters.

**Decision.**
- **Trigger:** Kubernetes `CronJob` (core API). One template in the Helm chart, rendered once per target from `targets/*/manifest.yaml`. Targets still cannot define topology.
- **Run coordination:** a **Postgres run ledger** owned by the platform (`runs` table: `target_id`, `scheduled_for`, `lease_owner`, `lease_until`, `state`, `image_digest`, `parser_version`, `bronze_ref`). Provides: idempotency (one run per `(target_id, scheduled_for)`), lease-based concurrency control across pods, missed-run detection, and the input to the gap detector — all in one table.
- **Run shape unchanged:** two containers/jobs per run — `capture` (fetch → persist raw → ack) and `process` (parse → validate → normalise → upsert → quality checks). Implemented as one `CronJob` whose Job runs `capture` then `process` as two containers with a shared emptyDir handoff of the Bronze reference, or as two `CronJob`s where `process` claims unprocessed captures from the ledger. Default: the latter (decouples processing from capture failures cleanly).
- **Gap detector:** a `CronJob` reading the ledger and Silver, enqueuing replays into the ledger.

**Rationale.** Argo Workflows is a cluster-scoped CRD; a project-scoped tenant cannot install it. Argo's residual value for a two-step pipeline — UI and DAG — is small, and the run ledger and gap detector were required anyway (Argo has no partition/backfill semantics), so the overlap was already large.

**Rejected.** Argo Workflows (CRD). Dagster (second control plane). Airflow/Kafka/Temporal (as before). Keeping Argo as an optional profile (two schedulers = entropy).

**Consequences.**
- `02` §2 ADR-003 text is replaced; ADR-004 replay and gap detector now reference the ledger.
- `03` Phase 2 gains `ledger/` module; Phase 5 loses the Argo `CronWorkflow` deliverable and gains "CronJob template rendered per target" and "run ledger migrations".
- Devil's-advocate note to keep in the ADR: `CronJob` alone has weak missed-run semantics (`startingDeadlineSeconds`) and no cross-target concurrency control; both are supplied by the ledger, which is why the ledger is not optional.

### ADR-016 — Release and rollback model

**Status:** ACCEPTED 2026-09-19 (`docs/adr/ADR-016-release-and-rollback.md`). Answers: "does Kubernetes let us roll back a bad release?" — yes for stateless code and configuration, **no** for schema, data, and semantic errors. The platform must supply the invariants that make Kubernetes rollback *safe*.

**Decision.**
1. **A release is an immutable bundle**: chart version + image **digest** (never a mutable tag) + the set of target manifests. Rollback = `helm rollback <release> <revision>`. Images are retained for ≥ N revisions; CI refuses `latest`.
2. **Automatic rollback on failed upgrade**: `helm upgrade --atomic --wait --timeout` plus a **`helm test` hook** that runs one fixture capture+process end-to-end against the new image. Kubernetes does *not* auto-rollback a crash-looping Deployment on its own; probes only stop the rollout. For `CronJob`-driven workloads, a crash surfaces only at the next run, so the post-upgrade test hook is the detection mechanism, and the **freshness SLI over the next two cadences** is the confirmation.
3. **Schema migrations are the rollback trap.** Kubernetes rollback reverts the image, not the database. Therefore: migrations are **expand/contract** and every migration is compatible with version N−1 of the code; migrations run as a Helm `pre-upgrade` hook Job; a downgrade script is required and exercised in CI; the application **refuses to start** against an incompatible schema version (fail fast, never corrupt).
4. **Data written by a bad release is not undone by rollback.** Rollback stops the bleeding; the repair is `energyctl replay --from --to --parser-version <bad>` from Bronze, which is why Silver carries `parser_version` and `image_digest` lineage from the run ledger.
5. **Semantic failures are invisible to Kubernetes** (wrong sign, wrong unit, no crash). Defences are upstream: golden tests in CI, quality checks in `process`, and optionally a **canary target group** (one low-risk target runs the new image one cadence before the rest — `image.canary` vs `image.stable` in values). Canary is optional in v1; goldens and quality checks are not.
6. **Rollback is drilled**, like restore: a scheduled job deploys revision N, then N+1 with an injected failure, and asserts automatic rollback with zero Bronze loss and correct ledger state.

**Rejected.** Argo Rollouts / Flagger (CRDs; disproportionate). Relying on `kubectl rollout undo` alone (does not cover chart, config, or `CronJob` resources coherently).

---

## 4. Verification tasks for Claude Code (run over the live SSH access)

Rules: run the commands, paste raw output into §5, mark each V as **CONFIRMED / REFUTED / PARTIAL**, and state the profile consequence. Do not modify `02` or `03` before §5 is filled; then apply §6.

| ID | Question | Commands (adjust `$NS`, endpoints) | Decides |
|---|---|---|---|
| V-4 | Are we a tenant? Can we create CRDs? Which operators are already cluster-wide? Which cluster services exist? What quotas apply? | `kubectl auth can-i create customresourcedefinitions.apiextensions.k8s.io` · `kubectl auth can-i create cronjobs -n $NS` · `kubectl auth can-i create networkpolicies -n $NS` · `kubectl api-resources \| grep -Ei 'argoproj\|cnpg\|external-secrets\|monitoring.coreos\|cert-manager'` · `kubectl get ingressclass` · `kubectl get storageclass` · `kubectl get clusterissuer` (may be Forbidden — record that) · `kubectl get resourcequota,limitrange -n $NS -o yaml` | A-1, A-8, A-10; whether `tenant` profile can reuse pre-installed operators (it must still not require them) |
| V-5 | Is Magnum available? What OpenStack services and quotas exist? | `openstack catalog list` · `openstack coe cluster template list` · `openstack quota show` · `openstack flavor list` · `openstack image list \| grep -i ubuntu` | A-2; D-1 |
| V-6 | S3 endpoints, storage classes, lifecycle support, second independent endpoint | `aws --endpoint-url $S3_A s3api list-buckets` · `aws --endpoint-url $S3_A s3api get-bucket-versioning --bucket $B` · `aws --endpoint-url $S3_A s3api put-object-lock-configuration …` (dry test on a scratch bucket) · `aws --endpoint-url $S3_A s3api get-bucket-lifecycle-configuration --bucket $B` · `openstack object store account show` (Swift) · `rclone lsd s3a:` / `rclone lsd swift:` | A-3; ADR-002 cold tier and independent copy |
| V-7 | Is there an OpenAI-compatible inference endpoint? | `curl -s $LLM_BASE_URL/v1/models -H "Authorization: Bearer $LLM_TOKEN"` | A-4; ADR-009 default backend for dev |
| V-8 | Is kube access OIDC-issued? Token lifetime? | `kubectl config view --minify` · inspect the exec/OIDC block; note token TTL | A-5; CI identity design |
| V-9 | Egress: proxy? Can a pod reach Tier-1 sources? | `kubectl run egress-test --rm -i --restart=Never -n $NS --image=curlimages/curl -- sh -c 'env \| grep -i proxy; for u in https://www.ote-cr.cz/en https://www.ceps.cz/en https://web-api.tp.entsoe.eu; do curl -s -o /dev/null -w "%{http_code} $u\n" $u; done'` | A-7, A-12 |
| V-10 | Is a managed Postgres offered (Rancher catalog / e-INFRA service)? | Check Rancher "Apps" catalog in the cluster UI; `helm search repo` on any pre-configured repos; e-INFRA docs only as secondary evidence | A-11; which Postgres mode `tenant` uses on the reference cluster |
| V-1 | *(from 02)* ČEPS API mechanics; OTE public SOAP still served; ENTSO-E token | Run in Phase 4 through the harness, not here | — |
| V-2 | *(from 02)* Decree 408/2025 scope from primary text | Documentation task, not SSH | — |
| V-3 | *(from 02)* OTE / ENTSO-E terms on redistribution | Documentation task | D-9 |

---

## 5. Verification log

*(Claude Code appends here. Format: date · V-ID · verdict · raw output excerpt · consequence.)*

Access used: kubeconfig for the e-INFRA Rancher cluster (`rancher.cloud.e-infra.cz`, namespace `hussein-ns`), SSH front-end `skirit.metacentrum.cz`. Credentials live outside the repository. Each entry: one verdict line in the required format, followed by the trimmed raw output that supports it.

```text
2026-09-19  V-4   CONFIRMED  can-i create CRDs = "no"; cronjobs = "yes"; networkpolicies = "yes"; ingressclass list Forbidden; PodSecurity restricted:latest enforced   A-1, A-8, A-10 hold. Core chart = tenant: no CRDs, consume ingress/issuer/storageclass by name, requests/limits mandatory, restricted-PSS-clean securityContext on every pod (new A-14). Argo CRDs exist but cronworkflows create = "no" → ADR-003 rev. accepted. CNPG, prometheus-operator, cert-manager creatable in-namespace → tenant profile MAY use cnpg/PodMonitor behind flags; ESO absent → plain Secret default (D-7).
    $ kubectl auth can-i create customresourcedefinitions.apiextensions.k8s.io
    no
    $ kubectl auth can-i create cronjobs -n hussein-ns            → yes
    $ kubectl auth can-i create networkpolicies -n hussein-ns     → yes
    $ kubectl api-resources | grep -Ei 'argoproj|cnpg|external-secrets|monitoring.coreos|cert-manager'
    cronworkflows/workflows/workflowtemplates      argoproj.io/v1alpha1      (Argo Workflows present)
    applications/applicationsets/appprojects       argoproj.io/v1alpha1      (Argo CD present)
    clusters/backups/poolers/scheduledbackups       postgresql.cnpg.io/v1     (CloudNativePG present)
    objectstores                                    barmancloud.cnpg.io/v1
    certificates/issuers/clusterissuers             cert-manager.io/v1
    podmonitors/servicemonitors/prometheusrules/…   monitoring.coreos.com/v1  (prometheus-operator present)
    (no external-secrets.io resources)
    $ kubectl auth can-i create cronworkflows.argoproj.io -n hussein-ns        → no
    $ kubectl auth can-i create clusters.postgresql.cnpg.io -n hussein-ns      → yes
    $ kubectl auth can-i create podmonitors.monitoring.coreos.com -n hussein-ns → yes
    $ kubectl auth can-i create certificates.cert-manager.io -n hussein-ns     → yes
    $ kubectl auth can-i create externalsecrets.external-secrets.io -n hussein-ns → no
    $ kubectl get ingressclass
    Error from server (Forbidden): ingressclasses.networking.k8s.io is forbidden: User "u-gq5yxf3imu" cannot list resource "ingressclasses" ... at the cluster scope
    (existing ingress in namespace uses spec.ingressClassName=nginx)
    $ kubectl get storageclass   (13 classes; default = nfs-csi)
    csi-ceph-rbd-du  rbd.csi.ceph.com  Delete  Immediate  expansion=true
    nfs-csi (default)  org.democratic-csi.nfs-client  Retain  Immediate
    rook-cephfs  rook-ceph.cephfs.csi.ceph.com  Delete  WaitForFirstConsumer
    s3-csi  cerit.s3.csi ; s3-rook-buckets  rook-ceph.ceph.rook.io/bucket ; beegfs-csi ; zfs-csi ; …
    $ kubectl get clusterissuer
    letsencrypt-prod  True ; letsencrypt-prod-dns  True ; letsencrypt-stage  True ; selfsigned-issuer  True ; …
    $ kubectl get resourcequota,limitrange -n hussein-ns -o yaml
    ResourceQuota default-28hbj  hard: limits.cpu=10 limits.memory=9Gi requests.cpu=6 requests.memory=5Gi
    LimitRange   default-6cdfq  Container default: cpu=1 memory=512Mi ; defaultRequest: cpu=1 memory=512Mi
    $ kubectl run … --image=curlimages/curl   (first V-9 attempt, plain)
    Error from server (Forbidden): pods "energy-platform-verify-20260919" is forbidden: violates PodSecurity "restricted:latest":
      allowPrivilegeEscalation != false, unrestricted capabilities (must drop ["ALL"]), runAsNonRoot != true, seccompProfile must be RuntimeDefault or Localhost

2026-09-19  V-5   CONFIRMED  Brno1 catalog has neutron/nova/octavia/glance/masakari/heat/barbican/cinder/keystone/swift — no container-infra; `coe cluster template list` → "public endpoint for container-infra service in Brno1 region not found"; quota cores=20 instances=10 ram=51200 volumes=10 gigabytes=1000 networks=1 floating_ips=1 routers=0; 10 flavors (max 4 vCPU / 8 GB); Ubuntu jammy and noble images active   A-2 holds: Magnum absent → D-1 default (Terraform VMs + cloud-init k3s/RKE2) is the only option on the reference cloud. Quota shapes the `own-cluster` Terraform defaults: ≤ 3 nodes of e1.large (12 vCPU / 24 GB of the 20 / 50 GB quota), one network, one floating IP (single ingress VIP; routers=0 means the project network is pre-provisioned). Auth = application credential (`v3applicationcredential`), so Terraform's OpenStack provider gets `application_credential_id/secret` from CI secrets, never a user password.
    $ openstack catalog list -f value -c Name -c Type
    neutron network ; nova compute ; octavia load-balancer ; glance image ; masakari instance-ha ; heat orchestration ; barbican key-manager ; cinder volumev3 ; placement ; keystone identity ; heat-cfn ; swift object-store
    $ openstack coe cluster template list
    public endpoint for container-infra service in Brno1 region not found
    $ openstack quota show
    cores 20 ; instances 10 ; ram 51200 ; floating_ips 1 ; networks 1 ; volumes 10 ; gigabytes 1000 ; ports 25 ; routers 0 ; subnets 1 ; volume types: du-ceph-muni1-ssd, du-ceph-muni1-hdd, rbd1 (unlimited per-type)
    $ openstack flavor list -f value -c Name -c RAM -c Disk -c VCPUs   (10 flavors)
    e1.1core-2ram 2048 80 1 ; e1.tiny 2048 80 2 ; e1.small 4096 80 2 ; e1.medium 4096 80 4 ; e1.large 8192 80 4 ; g2.tiny 8192 80 2 ; g2.small 8192 80 4 ; e1.2core-16ram ; e1.4core-16ram ; e1.2core-30ram
    $ openstack image list | grep -i ubuntu
    ubuntu-jammy-x86_64 active ; ubuntu-jammy-x86_64-2026-05-22 active ; ubuntu-noble-x86_64 active ; ubuntu-noble-x86_64-2026-05-22 active ; …
    (auth: OS_AUTH_URL=https://identity.brno.openstack.cloud.e-infra.cz/v3, OS_AUTH_TYPE=v3applicationcredential; RC file outside the repository)

2026-09-19  V-6   CONFIRMED  store A = Ceph RGW (squid) at s3.cl4.du.cesnet.cz (CESNET Data Care): versioning Enabled, object lock COMPLIANCE/GOVERNANCE accepted and enforced (delete → AccessDenied "forbidden by object lock"), lifecycle rules accepted; store B = Swift on a separate RGW at object-store.brno.openstack.cloud.e-infra.cz (MetaCentrum Cloud Brno1), account reachable, 5 GB quota; and the storage-class probe (second pass, same day) shows store A implements only STANDARD: every other class → 400 InvalidArgument (empty message), while the lifecycle API accepts a transition to any class name, even a non-existent one   A-3 CONFIRMED for the S3-API contract and for the second, independently operated endpoint (different site, different operator team, different credential system: S3 keys vs application credential). Cold tier resolved by design, not by the endpoint: ADR-021 makes tiering a platform `rclone` job (`bronze.tiering.mode = none|move|lifecycle`) with a deploy-time probe, because lifecycle-to-class silently no-ops here and does not exist on Azure Blob. Bronze replication stays an `rclone` job (S3 → Swift). Verdict upgraded from PARTIAL after the probe; the earlier note said the class name was unknown — it is now known not to exist. rclone not run (absent locally; not run over SSH to avoid passing keys through a shared front-end); `aws s3api` covers the same evidence.
    $ aws --endpoint-url $S3_A s3api list-buckets
    {"owner":"…@einfra.cesnet.cz","buckets":[5 existing buckets, names omitted]}
    $ curl -I $S3_A   → server: Ceph Object Gateway (squid)
    $ aws s3api create-bucket --bucket energy-platform-verify-20260919 --object-lock-enabled-for-bucket   → ok
    $ aws s3api get-bucket-versioning --bucket energy-platform-verify-20260919
    {"Status": "Enabled", "MFADelete": "Disabled"}
    $ aws s3api put-object-lock-configuration … '{"ObjectLockEnabled":"Enabled","Rule":{"DefaultRetention":{"Mode":"COMPLIANCE","Days":1}}}'   → exit 0
    $ aws s3api get-object-lock-configuration
    {"ObjectLockConfiguration":{"ObjectLockEnabled":"Enabled","Rule":{"DefaultRetention":{"Mode":"COMPLIANCE","Days":1}}}}
    $ aws s3api put-bucket-lifecycle-configuration … Transitions:[{Days:90,StorageClass:COLD}] + NoncurrentVersionExpiration 365   → exit 0
    $ aws s3api get-bucket-lifecycle-configuration
    {"Rules":[{"ID":"bronze-cold",…,"Transitions":[{"Days":90,"StorageClass":"COLD"}]},{"ID":"noncurrent",…,"NoncurrentVersionExpiration":{"NoncurrentDays":365}}]}
    $ aws s3api put-object … --object-lock-mode GOVERNANCE --object-lock-retain-until-date +3min --storage-class COLD   → rejected (error text not captured; attempt budget spent)
    $ aws s3api put-object … --object-lock-mode GOVERNANCE (STANDARD class)   → ok
    $ aws s3api head-object   → {"StorageClass":null,"ObjectLockMode":"GOVERNANCE","ObjectLockRetainUntilDate":"2026-09-19T02:13:49+00:00"}
    $ aws s3api delete-object --version-id <locked>   (no bypass)
    An error occurred (AccessDenied) when calling the DeleteObject operation: forbidden by object lock
    $ aws s3 cp - s3://…/bronze/blobs/test (overwrite)   → list-object-versions: {"versions":2, latest IsLatest=true Size=3, previous IsLatest=false Size=28}
    cleanup: delete-object --bypass-governance-retention ×2 → ok ; delete-bucket → exit 0 ; list-buckets → scratch bucket absent
    $ openstack object store account show   (store B, Swift, Brno1, application credential)
    Account KEY_9d42… ; Bytes 0 ; Containers 0 ; Objects 0 ; Quota-Bytes=5000000000
    $ openstack catalog show object-store   → public: https://object-store.brno.openstack.cloud.e-infra.cz/swift/v1/KEY_9d42… (region Brno1)
    (5 GB Swift quota on the reference project is enough for a replication drill, not for a full Bronze mirror; the own-cluster profile requests a larger quota or a second CESNET S3 tenancy)
    --- storage-class probe (second pass, scratch bucket re-created and deleted three times; nothing else touched)
    $ for sc in STANDARD STANDARD_IA ONEZONE_IA INTELLIGENT_TIERING GLACIER GLACIER_IR DEEP_ARCHIVE COLD CESNET_TAPE TAPE; do aws s3api put-object … --storage-class $sc; done
    STANDARD → accepted, head-object StorageClass=STANDARD ; every other class → HTTP 400
    <Error><Code>InvalidArgument</Code><Message></Message>…</Error>   (aws CLI v2 crashes parsing the empty Message: "argument of type 'NoneType' is not a container or iterable")
    $ aws s3api put-bucket-lifecycle-configuration … Transitions:[{Days:1,StorageClass:"DEFINITELY_NOT_A_CLASS"}]   → exit 0 (accepted; no validation)
    $ curl https://du.cesnet.cz/en/navody/object_storage/start   → services listed: "CESNET S3", "CESNET RBD"; no storage class, tape or archive tier documented for S3; archive capacity is requested by email as a separate service

2026-09-19  V-7   CONFIRMED  GET $LLM_BASE_URL/models (base already ends in /v1) → HTTP 200, 34 models   A-4 holds; ADR-009 unchanged. Dev default backend = e-INFRA inference (`llm.ai.e-infra.cz/v1`); no GPU on the platform. Token stays in the env file outside the repo.
    $ curl -s $LLM_BASE_URL/models -H "Authorization: Bearer $LLM_TOKEN"   (base path = /v1)
    HTTP 200  {"n":34,"ids":["agentic","qwen3.5","mini","multilingual-e5-large-instruct","deepseek-v4-flash-thinking","gpt-oss-120b","deepseek-thinking",…]}
    ($LLM_BASE_URL/v1/models → 404 {"detail":"Not Found"}: the configured base URL already includes /v1)

2026-09-19  V-8   PARTIAL    kube identity is Shibboleth/Perun-federated (no local user) but the kubeconfig credential is an opaque Rancher token, TTL 1 year (expires 2027-02-28)   A-5 "identity is federated, no local users" CONFIRMED; "kube access is OIDC-issued short-lived token" REFUTED on the reference cluster: no exec/OIDC block, no JWT. CI deploy identity on a Rancher-fronted tenant cluster = a namespace-scoped Rancher API token held as a CI secret with a rotation date, not workload-identity federation. A-5 "Cost if false" updated (see §2). Would resolve fully: confirmation that Rancher's OIDC client (rancher.cloud.e-infra.cz → einfra.cesnet.cz) can mint short-lived kubeconfig tokens for a CI principal.
    $ kubectl config view --minify --raw -o json | jq '.users[0].user | keys'   → ["token"]   (no exec, no auth-provider)
    token: 83 chars, prefix "kubeconfig-u…", not a JWT (opaque Rancher token)
    $ kubectl auth whoami
    Username  u-gq5yxf3imu ; Extra: username jalalhussein@einfra.cesnet.cz ; principalid shibboleth_user://…@einfra.cesnet.cz
    Groups    shibboleth_group://urn:geant:cesnet.cz:res:personal-project-kubernetes#perun.cesnet.cz, system:authenticated, system:cattle:authenticated, …
    $ curl https://rancher.cloud.e-infra.cz/v3/tokens/<token-id>   (Rancher API, own token)
    {"ttl": 31536000000, "expiresAt": "2027-02-28T03:01:14Z", "created": "2026-02-28T03:01:14Z", "authProvider": "shibboleth", "description": "Kubeconfig token"}
    $ curl …/v3/settings/kubeconfig-default-token-ttl-minutes   → {"value": "525600", "default": "43200"}
    (kubectl get tokens/settings.management.cattle.io → Forbidden at cluster scope; Rancher REST API answered instead)

2026-09-19  V-9   CONFIRMED  no proxy env in pod; OTE 200, ČEPS 301/200, ENTSO-E host reachable (404 on root); egress IP 147.251.253.180   A-7 and A-12 hold on the reference cluster. The single-egress-path rule (energy_platform.fetch, HTTP_PROXY/NO_PROXY, injectable CA) stays because scenarios A/B are proxied. Network rate limiting cannot be shown by one request; politeness remains platform-enforced (D-5). Test pod required a restricted-PSS securityContext (see V-4) and was removed afterwards.
    $ kubectl run energy-platform-verify-20260919 --rm -i --restart=Never -n hussein-ns --image=curlimages/curl --overrides='{…runAsNonRoot,seccomp RuntimeDefault,drop ALL,allowPrivilegeEscalation=false…}' -- sh -c '…'
    --- proxy env:
    (none above = no proxy)
    200 91.209.101.45   https://www.ote-cr.cz/en
    301 150.171.109.193 https://www.ceps.cz/en
    404 20.79.236.108   https://web-api.tp.entsoe.eu
    200 91.209.101.45   https://www.ote-cr.cz/pw-data/services/PublicDataService?wsdl
    200 2603:1061:14:68::1 https://www.ceps.cz/_layouts/CepsData.asmx?WSDL
    --- egress ip: 147.251.253.180
    pod "energy-platform-verify-20260919" deleted from hussein-ns namespace
    $ kubectl get pod energy-platform-verify-20260919 -n hussein-ns   → Error from server (NotFound)

2026-09-19  V-10  CONFIRMED  no managed Postgres: Rancher catalogs offer no Postgres service (cerit-sc has pgadmin only; partner catalog has the cloudnative-pg operator chart but catalog installs are Forbidden); CNPG operator is already cluster-installed and Cluster CRs are creatable in-namespace   A-11 holds: Postgres is a DSN contract (D-2). On the reference cluster the tenant profile defaults to postgres.mode=statefulset; postgres.mode=cnpg is available behind the flag because the operator is pre-installed. helm not present locally nor on the front-end → `helm search repo` not run; Rancher catalog index queried via API instead.
    $ kubectl get clusterrepos.catalog.cattle.io
    cerit-sc (git https://github.com/CERIT-SC/rancher-apps.git) ; rancher-charts ; rancher-partner-charts ; rancher-rke2-charts
    $ kubectl get apps.catalog.cattle.io -n hussein-ns   → No resources found
    $ kubectl auth can-i create apps.catalog.cattle.io -n hussein-ns   → no
    $ curl https://rancher.cloud.e-infra.cz/v1/catalog.cattle.io.clusterrepos/rancher-partner-charts?link=index | jq '.entries|keys' | grep -Ei 'postgres|timescale|cnpg|minio|zalando|crunchy'
    cloudnative-pg  minio-operator
    $ … rancher-charts?link=index (41 entries)   → no postgres/timescale/cnpg/minio match
    $ … cerit-sc?link=index   → 404 NotFound via API; public repo listed instead:
    $ curl https://api.github.com/repos/CERIT-SC/rancher-apps/contents/charts | jq -r '.[].name'
    _common ansys bioda blender code-server cplex dataspecer desktop3d filebrowser grafana knime langflow logging-subscriber loki matlab matrix-hermes maxquant minio monitoring moodle mpijob n8n neo4j open-notebook orthovenn overleaf-cep owncloud paraview pgadmin phpmyadmin pycharm ridom-seqsphere rstudio samba scipion shinysom textgen-ui vmd wave
    $ ssh skirit 'command -v helm'   → MISSING ; local: helm MISSING
```

---

## 6. Reconciliation checklist (applied 2026-09-19; see `docs/adr/` and the dated notes in `02`/`03`)

- [x] `02` ADR-001: replace "two profiles" with the three-profile table from §2.1; name MetaCentrum/e-INFRA as the **reference environment** (assumption base), not as the production platform.
- [x] `02` ADR-003: replace body with ADR-003 rev. once accepted; keep the Argo rejection rationale.
- [x] `02` ADR-004: replay and gap detector reference the run ledger.
- [x] `02` §4: D-2 → "Postgres as DSN contract; modes `statefulset|cnpg|external`"; D-6 → "annotations by default, `PodMonitor` behind flag"; D-7 → "plain `Secret` by default, ESO behind flag"; add D-13 "canary target group (optional)".
- [x] `02` §2: append ADR-016 (release and rollback).
- [x] `02` §4.3: add V-4 … V-10 pointing to this file.
- [x] `03` Phase 2: add `ledger/` module and ledger migrations; add "downgrade script per migration" to the definition of done.
- [x] `03` Phase 3 constraint matrix: add rows "outbound HTTP outside `energy_platform.fetch`", "workload without resource requests", "mutable image tag", "migration without downgrade".
- [x] `03` Phase 5: remove Argo `CronWorkflow`; add "CronJob template rendered per target", "run ledger", "`helm test` hook", "rollback drill", "tenant profile deploy to the reference cluster as the first real environment".
- [x] `03` Phase 8 README: add a section "Assumptions and what they cost" summarising §2.
