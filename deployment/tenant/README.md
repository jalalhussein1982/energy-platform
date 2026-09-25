# `tenant` profile — a namespace on a shared cluster (ADR-001 amend)

No cluster rights, no CRDs, everything consumed by name or declared by CIDR. `values-tenant.yaml`
is the base; `values-<env>.yaml` layers an environment on it:

| Environment | File | Where | Deployed by |
|---|---|---|---|
| **demo** (ADR-028) | `values-demo.yaml` | the Hetzner k3s cluster from `roots/hcloud`, namespace `energy-platform`, namespace-scoped `Role` | `.github/workflows/deploy-demo.yml` → `make deploy-demo` (GitHub OIDC, V-14) or the author with an admin kubeconfig |
| reference (e-INFRA Rancher) | — | **no release** (ADR-028: one-off probes only) | — |

```bash
make deploy-tenant ENV=demo KUBECONFIG=~/.kube/demo.yaml    # any kubeconfig with namespace rights
make deploy-demo                                            # inside GitHub Actions: OIDC kubeconfig, then deploy-tenant ENV=demo
```

Every deploy: `render_target_values` → `helm upgrade --install` with rollback-on-failure and
`--wait --wait-for-jobs`; the hook chain (`migrate` → `smoke`) gates the release (ADR-025).

## Layer-1 egress on a shared cluster (ADR-026, V-11)

The chart **declares** the NetworkPolicies (default deny, DNS, Postgres, object store, TCP 443
to public ranges for the fetching pods only). **V-11 CONFIRMED (2026-09-23):** the reference
cluster's CNI (Calico) enforces egress policy for a tenant namespace: a probe pod reached OTE,
was cut off by a label-scoped default-deny, and reached it again once the policy was removed
(`00` §5). Layer 2 (host allowlist, redirect and private-range checks in
`energy_platform.fetch`) stays the per-host control.

Enforcement can lag a pod's start. On the demo (k3s, embedded kube-router) the same test found a
new pod's **first packets unfiltered** for up to about a second, with the metadata service
reachable. So `egress.policyGate.enabled` (on in `values-demo.yaml`) makes every platform pod
wait in an init container until its policy is in force (ADR-026 amendment 2, `05` C-65). Turn it
on for any CNI that applies policy asynchronously. `deployment/local/egress-test-job.yaml`
measures the CNI itself (ungated; the same three assertions as `make local-egress-test`).

## Demo deploy identity (V-14, ADR-015)

`.github/workflows/deploy-demo.yml` has two jobs, each with one permission (plan P5-D20):
`image` (`packages: write`) runs `make image-push` on the amd64 runner — the `cx23` nodes'
architecture — and pushes `ghcr.io/<owner>/<repo>` with the job's own `github.token`; `deploy`
(`id-token: write`) takes that digest as `IMAGE_DIGEST`. `scripts/oidc_kube_context.sh` asks
GitHub for a token with audience `energy-platform-demo`, builds a kubeconfig from it and the
public cluster CA, and the API server maps it to `gha:<owner>/<repo>` with the namespace Role
from cloud-init. Repository **variables** (not secrets, all public or non-sensitive):
`DEMO_CLUSTER_URL`, `DEMO_CLUSTER_CA`, `DEMO_OCI_NAMESPACE` (store B's endpoint is built from it;
the tenancy namespace is not committed). Nothing long-lived is stored in GitHub.

The demo values carry no placeholders (plan P5-D22): the object-store egress CIDRs are the
providers' published ranges (see the comments in `values-demo.yaml`), and the render fails
loudly if `DEMO_OCI_NAMESPACE` is missing. The package is private like the repository, so the
pods pull with `image.pullSecrets: [ghcr-pull]` (P5-D21).

## Author checklist before the first demo deploy (Level 3 items)

*(2026-09-23: all done — the agent ran them with the CLIs at the author's request; the demo is
live. What it took is in `docs/07-operations.md` §4.1.)*

1. `terraform apply` the `hcloud` plan (`deployment/own-cluster/README.md`), then read
   `terraform output demo_cluster_url` and fetch the CA from the server.
2. Repository variables `DEMO_CLUSTER_URL` and `DEMO_CLUSTER_CA` from step 1
   (`gh variable set DEMO_CLUSTER_URL --body …`; `gh variable set DEMO_CLUSTER_CA < ca.crt`).
   The repository, the `demo` environment and `DEMO_OCI_NAMESPACE` exist already (2026-09-23).
3. With the admin kubeconfig (`ssh root@<server> cat /etc/rancher/k3s/k3s.yaml`, server address
   replaced by the public one), create the two Secrets in the namespace
   (`make print-demo-secret-template` prints both commands): `energy-platform` with
   `POSTGRES_PASSWORD` (new, e.g. `openssl rand -hex 16`), `BRONZE_ACCESS_KEY_ID` /
   `BRONZE_SECRET_ACCESS_KEY` (Hetzner S3 keys, `verify.env`), `BRONZE_REPLICA_ACCESS_KEY_ID` /
   `BRONZE_REPLICA_SECRET_ACCESS_KEY` (OCI customer secret key, `verify.env`); and `ghcr-pull`
   from a classic GitHub PAT with `read:packages` only (set an expiry).
4. Run the `deploy-demo` workflow once by hand (`gh workflow run deploy-demo`); then switch it
   to `push: main`. *(Done 2026-09-23, Phase 9: it runs on every push to `main` that touches
   the platform, a target, the chart, the tenant values, the image, the lock file or the
   Makefile, and still by hand.)*

The image build needs nothing from you: the workflow pushes it. A deploy from the laptop with
the admin kubeconfig is `make deploy-tenant ENV=demo KUBECONFIG=… DEMO_OCI_NAMESPACE=…
IMAGE_REPO=ghcr.io/<owner>/<repo> IMAGE_DIGEST=sha256:…` (the digest of an image the workflow
pushed; a laptop build would be arm64).

## Alerting on the demo (ADR-040, 2026-09-25)

`values-demo.yaml` sets `alerting.enabled: true` with `alerting.kubeStateMetrics.apiServer.cidrs:
[10.43.0.1/32, 10.10.1.10/32]` and `ports: [443, 6443]` (the `kubernetes` Service IP as the pod
addresses it and the k3s server's endpoint on the private network — `kubectl get endpoints
kubernetes`; kube-router evaluates after the Service translation, so the second is the one that
matters there, and both are harmless).
The deploy identity may not manage Roles (ADR-035 amendment 1), so `alerting.kubeStateMetrics.rbac.create`
is `false` on the demo and the admin applies the Role and RoleBinding once:

```bash
kubectl --kubeconfig <admin> apply -f deployment/tenant/demo-kube-state-metrics-rbac.yaml
```

The push then renders Prometheus, kube-state-metrics (bound to that Role), Alertmanager and the
platform receiver in the namespace (three new images pulled by digest). The author then runs the delivery drill there
(the Job in `deployment/local/drills/alert.sh`, `kubectl logs deploy/energy-platform-alert-sink`)
and wires a real channel by values: `alerting.alertmanager.receivers` / `routes` (raw Alertmanager
objects) plus `alerting.alertmanager.egress.cidrs` for an external receiver. The receiver's log is
the delivery record until then.

**The channel's credential is a Secret, never a value (ADR-040 amendment 1, Phase 14).**
`values-demo.yaml` names `alerting.alertmanager.existingSecret: energy-platform-alertmanager`, mounted
read-only and optional at `/etc/alertmanager/secrets/` — the release runs before the Secret exists. The
author creates it once (Level 3):

```bash
kubectl -n energy-platform create secret generic energy-platform-alertmanager --from-literal=smtp-password='…'
```

then adds the receiver (`auth_password_file: /etc/alertmanager/secrets/smtp-password`), the routes and
the egress netblocks on port 587 as `deployment/helm/energy-platform/ci/receiver-values.yaml` shows —
its routes keep the two uncalibrated night-time freshness alerts (`ote_dam`, `ote_imbalance_settlement`)
in the log only and send every page to the channel *and* the log. A credential typed into values, or a
route naming a receiver that is not declared, fails `helm template` before anything is pushed. The
runbook, with the netblock lookup and the mailbox drill, is `docs/07-operations.md` §7.3.
On the demo the values are set (2026-09-26): the receiver `ops-email` sends through Gmail's
submission service (`smtp.gmail.com:587`, the author's account to itself, an app password in the
Secret) and the egress netblocks are every IPv4 prefix of Google's published `goog.json` — the SPF
record does not cover the submission host (§7.3 step 1).
