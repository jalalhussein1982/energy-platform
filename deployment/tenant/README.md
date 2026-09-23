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
to public ranges for the fetching pods only). Whether the cluster's CNI **enforces** egress
policy is V-11, still open for the reference cluster; until CONFIRMED the claim for that
profile is "declared, enforcement unverified", and layer 2 (host allowlist, redirect and
private-range checks in `energy_platform.fetch`) is the control known to hold. On the demo
cluster k3s's embedded policy controller enforces it, and `deployment/local/egress-test-job.yaml`
can be applied there to prove it (the same three assertions as `make local-egress-test`).

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
   to `push: main`.

The image build needs nothing from you: the workflow pushes it. A deploy from the laptop with
the admin kubeconfig is `make deploy-tenant ENV=demo KUBECONFIG=… DEMO_OCI_NAMESPACE=…
IMAGE_REPO=ghcr.io/<owner>/<repo> IMAGE_DIGEST=sha256:…` (the digest of an image the workflow
pushed; a laptop build would be arm64).
