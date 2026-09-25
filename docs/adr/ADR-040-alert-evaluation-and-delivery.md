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
     `RoleBinding` — no ClusterRole, no cluster right, the tenant contract kept;
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
