# ADR-040 — Alert evaluation and delivery in the chart: a rule nobody evaluates is documentation

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-25 |
| Resolves | review 3 R3 (`codex-review/01-deep-review.md`); completes ADR-037 §4 (the rules), ADR-036 amendment 2 (the staleness rules) and A-6 (freshness alerting as the operator interface) |
| Supersedes | — |

## Context

ADR-037 §4 defined twelve alert rules and shipped them two ways: a `PrometheusRule` behind
`metrics.operator.enabled` (CRDs, for a cluster that already runs the Prometheus operator) and a
plain ConfigMap "for any scraper". ADR-036 amendment 2 added three staleness rules over
kube-state-metrics. No profile ran a scraper: the demo sets `metrics.operator.enabled=false`,
its live inventory (review 3, `codex-review/evidence/live-workloads.log`) holds the exporter
and Grafana and nothing that evaluates a rule, five of the twelve rules read `kube_*` metrics
that nothing exports, and the final report said the rules "watch". A-6 makes freshness
alerting the only operator interface of a best-effort service; a stopped backup, a broken
replication, a failed drill or a late target was visible only to someone opening a dashboard.

Constraints that shape the answer: the core chart needs no CRD and runs as a tenant (ADR-001
amendment; ADR-003 rev.); every image is pinned by digest and every pod passes the restricted
profile (05 C-43, C-57); pods start under default-deny NetworkPolicies (ADR-026); the sources
allow internal use only, so nothing here gets a public address (06 §1.4, §4.5, ADR-039); the
platform's Python package owns every socket (ADR-027 §3) and adds no dependency without an ADR.

## Decision

1. **`alerting.enabled`** (off in the tenant default; on in `local`, on the demo, on in the
   all-flags render) renders four Deployments, their Services, ConfigMaps and NetworkPolicies:
   - **Prometheus** (`docker.io/prom/prometheus` v3.14.0 by digest, uid 65534, read-only root,
     an `emptyDir` TSDB with two days of retention — the alerts are evaluated live, the history
     is not the point) loads the existing `<release>-alert-rules` ConfigMap **unchanged** as its
     rule file and scrapes the exporter and kube-state-metrics every minute;
   - **kube-state-metrics** (`registry.k8s.io/kube-state-metrics/kube-state-metrics` v2.20.0 by
     digest) **namespaced**: `--namespaces=<release namespace> --resources=cronjobs,jobs`, its
     own ServiceAccount, a `Role` with `list`/`watch` on `batch` `jobs` and `cronjobs` and a
     `RoleBinding` — no ClusterRole, no cluster right, the tenant contract kept. A deploy
     identity that may not manage Roles (the demo's OIDC identity, ADR-035 amendment 1, which
     the first deploy of this ADR proved: Helm's pre-flight `get` on the Role was forbidden and
     the release stayed untouched) sets `alerting.kubeStateMetrics.rbac.create: false` and the
     cluster admin applies `deployment/tenant/demo-kube-state-metrics-rbac.yaml` once — the
     identity stays as narrow as it was rather than gaining `roles`/`rolebindings` verbs;
   - **Alertmanager** (`docker.io/prom/alertmanager` v0.34.1 by digest, uid 65534) routes every
     alert, grouped by alert name and target, to the **platform receiver** and to whatever the
     operator adds by values (`alerting.alertmanager.receivers`, `alerting.alertmanager.routes`:
     raw Alertmanager receiver and route objects — SMTP, a webhook); `send_resolved` is on;
   - the **platform receiver** — `energyctl alert-sink`, a Deployment on the platform image
     (`energy_platform/fetch/alert_sink.py`: the package that owns sockets, next to the policy
     gate) that answers Alertmanager's webhook and writes **one JSON line per delivery** to its
     log (`firing`/`resolved`, alert names, labels, the instants). Its log is the delivery
     record; it holds no credential and no platform environment.
2. **Network.** Default-deny stays. Prometheus → the exporter (9187), kube-state-metrics (8080)
   and Alertmanager (9093); kube-state-metrics → the API server, declared by the tenant as
   `alerting.kubeStateMetrics.apiServer.cidrs` and `ports` — the `kubernetes` Service IP on
   443 as the pod addresses it **and** the endpoint on 6443 as the node serves it (`kubectl get
   endpoints kubernetes`; the demo `10.43.0.1/32` + `10.10.1.10/32`, kind `10.96.0.1/32` +
   `172.16.0.0/12`), because a CNI evaluates the policy before or after Service translation
   and kube-state-metrics found the difference on kind (`10.96.0.1:443: i/o timeout`); Cilium
   additionally needs `policyCIDRMatchMode: [nodes]` to match a rule that names a node, loaded
   by a restarted agent (`rollOutCiliumPods: true`; a config change alone left the old agent
   running and the rule dead, 2026-09-25) — and
   **required** when the flag is on: the render fails without it; Alertmanager → the receiver
   (8080) and, for an external receiver, `alerting.alertmanager.egress.cidrs`/`ports` (empty by
   default: no internet); Grafana → Prometheus (9090) for the ADR-037 `freshness.json` dashboard,
   which the chart now provisions with the Prometheus datasource when the flag is on; ingress to
   Prometheus and Alertmanager from the namespace only (a port-forward enters from the node, as
   with Grafana). No Ingress, no LoadBalancer, no NodePort.
3. **The delivery drill** (`make alert-drill`, `deployment/local/drills/alert.sh`): a Job named
   `<release>-restore-drill-manual-fail` whose one container exits 1; within about two minutes
   `EnergyPlatformRestoreDrillFailed` is delivered `firing` to the receiver (kube-state-metrics
   → Prometheus, `for: 1m` → Alertmanager → webhook); the Job deleted, `resolved` follows. The
   drill exits 1 unless both deliveries are in the receiver's log. It runs on kind in the gate
   (`docs/07` §7.2) and is the author's on the demo (Level 3).
4. **What is not decided here:** which real channel an operator wires (values), and the
   operator's on-call process. The receiver proves delivery; it does not page a person.
5. **The first live evaluation corrected two rules (2026-09-25).** On the demo the drill and
   replication failure rules read `kube_job_status_failed{…} > 0` — "any failed Job of the
   kind" — and paged at once for the two restore-drill Jobs of 2026-09-24 that failed and were
   kept in the namespace as records (`failedJobsHistoryLimit`, a manual retry), although the
   third run that night had succeeded. Both rules now fire only when the **newest** Job of the
   kind is a failed one (`max(kube_job_created … and on (job_name) (kube_job_status_failed > 0))
   == max(kube_job_created …)`) and resolve on the next success; the delivery drill's Job is
   the newest while it exists, so the drill is unchanged.

## Rationale

The rules already existed and named their metric source; the smallest honest completion is to
run an evaluator that loads them as they are — one definition, still shipped two ways — with the
metric source the staleness rules named, inside the chart's own posture. Reusing Grafana as the
evaluator would have meant re-expressing every rule in a second format (drift), and Grafana's
own Alertmanager needs Prometheus anyway. A receiver on the platform image keeps the proof of
delivery inside the chart with no fourth third-party image and no external service; the real
channel is a values change because it is the operator's, and its secret does not belong in a
chart default. A namespaced kube-state-metrics is the difference between a tenant and a cluster
admin; the API-server CIDR is the price of default-deny for a component that must read the
control plane, and a tenant knows that address.

## Rejected

- **Leave the rules as documentation and note "external Prometheus expected"** — the review's
  point: a rule nobody evaluates protects nothing, and the demo is the environment the report
  describes.
- **kube-prometheus-stack / the Prometheus operator in the demo** — CRDs and cluster-wide
  rights; the core chart's tenant contract is the argument the platform makes.
- **Platform-computed backup and replication ages instead of kube-state-metrics** — rejected
  already in ADR-036 amendment 2 (the copies live in object storage, not Postgres; the Job's
  success is what is known); revisited and kept: it would move the check into the platform
  without removing the evaluator.
- **Grafana unified alerting as the evaluator** — a second rule format to keep in step with
  the ConfigMap; no evaluator saved.
- **A public echo service as the receiver** — an alert names targets and ages, which is
  internal operational data, and the proof would depend on a third party.
- **A ClusterRole for kube-state-metrics** — cluster rights the tenant profile does not have.

## Consequences

- Chart: `templates/alerting.yaml`, the `alerting` and three `resources.*` values, the Grafana
  datasource and dashboard additions, `values-local.yaml`, `values-demo.yaml`,
  `ci/all-flags-values.yaml`; `05` rows C-72…C-75; `docs/07` §7 and §7.2; the chart and tenant
  READMEs.
- Library: `energy_platform/fetch/alert_sink.py`, `energyctl alert-sink` (a listener, no
  egress; the `http` import lives in `fetch/` where ADR-027 §3 allows it).
- Demo: the author's next push renders the four workloads (three new images pulled by digest)
  and the author runs the delivery drill there; a real receiver (SMTP or a webhook) is a values
  change with its egress CIDR.
- Devil's advocate: three more third-party images to keep pinned (the MinIO lesson of ADR-036
  amendment 4 applies: a withdrawn image fails the pull, never the data); Prometheus's TSDB is
  an `emptyDir`, so a restart loses the (two-day) history and re-evaluates `for:` windows from
  zero — an alert in its `for` window at restart fires up to that window later; the receiver's
  log is the delivery record and lives as long as the pod's log does — an operator who needs a
  durable record wires a real receiver.

## Verification refs

`tests/harness/test_chart.py::test_alerting_renders_behind_its_flag_without_cluster_rights`,
`tests/fetch/test_alert_sink.py`; the delivery drill on kind recorded in `docs/07` §7.2.

## Amendment 1 (2026-09-25) — the operator's channel: its credential in a Secret, its routing tested, two refusals at render

**Finding (post-review advice of 2026-09-25, item 2; Phase 14).** §1 left the real channel to
`alerting.alertmanager.receivers` / `routes`, raw Alertmanager objects rendered with `toYaml`
into the `<release>-alertmanager` ConfigMap; the Deployment mounted that ConfigMap and an
`emptyDir`, nothing else. An authenticated SMTP receiver or a token-bearing webhook therefore
had nowhere to put its credential but the ConfigMap and the values file — world-readable in the
namespace and committed in Git. §4 said which channel an operator wires is not decided here;
how one is wired *without leaking its credential* was not decided either. Two more things the
first live cycle raised (`docs/07` §4.4): `EnergyPlatformTargetLate` paged at 01:45 UTC for
`ote_dam` and `ote_imbalance_settlement`, two targets whose publication expectation the
freshness code documents as uncalibrated (a day-ahead target's lateness is detected up to a day
late; the daily settlement's publication timing is `[UNVERIFIED]`, `01` §10); and a `routes`
entry naming a receiver that does not exist is refused by Alertmanager only at load — the pod
never ready, the upgrade gate rolling back, the reason three `kubectl` commands away.

**Decision.**

1. **`alerting.alertmanager.existingSecret`** names a Secret the operator creates in the release
   namespace. The Deployment mounts it read-only at `/etc/alertmanager/secrets`, one file per
   key, `optional: true` — the pod starts before the Secret exists and the files appear when it
   does. Receivers reference the files through Alertmanager's own `*_file` fields
   (`auth_password_file`, `url_file`, `api_url_file`, `webhook_url_file`,
   `http_config.basic_auth.password_file`, `http_config.authorization.credentials_file`), read
   at send time, so the configuration loads without them. A dedicated Secret rather than
   `secrets.existingSecret`: Alertmanager holds no platform credential (§1, the receiver side).
   The demo names `energy-platform-alertmanager`.
2. **Two refusals at render.** A credential-bearing key anywhere under
   `alerting.alertmanager.receivers` (`auth_password`, `auth_secret`, `password`,
   `credentials`, `bearer_token`, `api_key`, `api_secret`, `api_url`, `webhook_url`,
   `routing_key`, `service_key`, `token`, `user_key`) fails the render and names the `*_file`
   alternative without echoing the value (`05` C-76). A route at any depth whose `receiver` is
   neither `platform-sink` nor a declared receiver fails the render by name (`05` C-77). A
   plain webhook `url` is not refused — the platform receiver and an internal endpoint use one
   — so a URL that carries a token belongs in the Secret and is read as `url_file`.
3. **The interim routing for the two uncalibrated freshness alerts is a values example**,
   `ci/receiver-values.yaml`, rendered by the chart test and walked the way Alertmanager walks
   a routing tree (the first matching child, its siblings while `continue: true`, the parent's
   receiver only when no child matches): `EnergyPlatformTargetLate` for `ote_dam` and
   `ote_imbalance_settlement` → `platform-sink` only (logged, not paged); `severity = page` →
   the operator's channel with `continue: true`; a catch-all → `platform-sink`, so the
   receiver's log stays the delivery record of every alert. No rule changes: the calibration is
   a publication expectation in the manifest, read by freshness (Phase 15, an ADR-037
   amendment), not a wider `for:` and not a silenced night.
4. **The runbook for the demo** is `docs/07` §7.3: the Secret, the values, the egress
   netblocks on the authenticated submission port (Hetzner Cloud blocks outbound port 25 by
   default; a provider behind rotating addresses is allow-listed by its published netblocks),
   then the drill of §7.2 ending in a mailbox rather than a log.

**Consequences.** Chart: `templates/alerting.yaml` (the mount, the two refusals),
`values.yaml`, `values-demo.yaml`, `ci/receiver-values.yaml`; `05` C-76, C-77; tests
`test_the_operators_receiver_credential_is_a_secret_file_never_a_value`,
`test_a_credential_typed_into_receiver_values_is_refused_at_render`,
`test_a_route_naming_an_undeclared_receiver_is_refused_at_render`,
`test_the_interim_night_routing_pages_failures_and_logs_the_uncalibrated_freshness`. The demo:
the author creates the Secret and sets the receiver values (Level 3); until then the push
changes nothing there but an empty optional mount. Devil's advocate: the key list is a
denylist and Alertmanager grows integrations, so a new integration's secret field would pass
until the list is extended — the refusal is the gate for the common case, the Secret mount is
what makes the right way the easy way; the routing walk in the test re-implements
Alertmanager's tree semantics rather than calling `amtool`, which is not in the toolchain,
and the test's docstring says so.
