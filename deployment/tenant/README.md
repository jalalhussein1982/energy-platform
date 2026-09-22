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

The workflow has `id-token: write` and nothing else. `scripts/oidc_kube_context.sh` asks
GitHub for a token with audience `energy-platform-demo`, builds a kubeconfig from it and the
public cluster CA, and the API server maps it to `gha:<owner>/<repo>` with the namespace Role
from cloud-init. Repository **variables** (not secrets, both public): `DEMO_CLUSTER_URL`,
`DEMO_CLUSTER_CA`.

## Author checklist before the first demo deploy (Level 3 items)

1. `terraform apply` the `hcloud` root (`deployment/own-cluster/README.md`), then read
   `terraform output demo_cluster_url` and fetch the CA from the server.
2. Create the GitHub repository for this checkout and push `main` (this working copy has no
   remote yet); set the two repository variables; create the `demo` environment.
3. Build and push the platform image to `ghcr.io/<owner>/energy-platform` (the workflow's
   `IMAGE_REPO`), by digest: `make image IMAGE_REPO=ghcr.io/<owner>/energy-platform && docker push …`.
4. In the namespace, create the Secret from the Terraform outputs and the V-12/V-13 keys:
   `POSTGRES_PASSWORD`, `BRONZE_ACCESS_KEY_ID`, `BRONZE_SECRET_ACCESS_KEY`,
   `BRONZE_REPLICA_ACCESS_KEY_ID`, `BRONZE_REPLICA_SECRET_ACCESS_KEY` (`make print-demo-secret-template`).
5. Replace the `REPLACE_*` placeholders in `values-demo.yaml` (OCI namespace, the two stores'
   address ranges) with `--set` at deploy time or a values file outside the repository.
6. Run the `deploy-demo` workflow once by hand; then switch it to `push: main`.
