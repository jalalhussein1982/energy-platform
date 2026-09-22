# `own-cluster` profile — Terraform provisions, Helm deploys (ADR-001 amend, ADR-035)

Two roots over the same module contracts (`network`, `nodes`, `storage`, `security`, each with
an `hcloud` and an `openstack` variant exposing identical inputs and outputs), one shared
cloud-init that installs a pinned k3s with GitHub-OIDC structured authentication
(`terraform/cloud-init/`):

| Root | Environment | CI | Applied |
|---|---|---|---|
| `terraform/roots/hcloud` | **demo** (ADR-028): 2 × `cx23` in `nbg1`, private network, firewall, 10 GB Postgres volume, bucket A on Hetzner Object Storage (Object Lock COMPLIANCE), bucket B on OCI Frankfurt (retention rule, versioning off) | `terraform validate` + `terraform test` with mock providers | **by the author only** |
| `terraform/roots/openstack` | reference cloud (MetaCentrum Brno1, V-5) | same | **never** (ADR-028) |

```bash
make terraform-validate            # fmt -check, init -backend=false, validate, test (mocks) — both roots
make terraform-plan-hcloud         # plan -out ~/.config/energy-platform/plans/hcloud-<date>.tfplan (agent-run)
# author only:
terraform -chdir=deployment/own-cluster/terraform/roots/hcloud apply ~/.config/energy-platform/plans/hcloud-<date>.tfplan
```

The Makefile uses `terraform` or, when absent, `tofu` (OpenTofu ≥ 1.8 supports the same
`test`/`mock_provider` features).

## Cost guard (ADR-028 §5) — before the first `apply`

| Account | Ceiling | What runs | Estimate (2026-09) |
|---|---|---|---|
| Hetzner Cloud | **€25 / month** budget alert in the console | 2 × `cx23` (≈ €3.79 each), one 10 GB volume (≈ €0.50), one primary IPv4 (≈ €0.60), Object Storage (≈ €5 base incl. 1 TB, at demo volume) | ≈ €14 / month |
| OCI | **€10 / month** budget alert in the console | Object Storage store B within the Always Free 20 GB; egress within the free allowance at demo volume | ≈ €0 / month |

Author checklist, in this order:

1. Create the budget alerts in both consoles at the ceilings above.
2. Export the variables the root needs (never commit them): `TF_VAR_hcloud_token`,
   `TF_VAR_hetzner_s3_access_key`, `TF_VAR_hetzner_s3_secret_key`, `TF_VAR_admin_cidr`,
   `TF_VAR_ssh_public_key`, `TF_VAR_github_repository`, `TF_VAR_oci_compartment_id`,
   `TF_VAR_oci_namespace`; the OCI provider reads `~/.oci/config` (`oci_config_profile`).
   `~/.config/energy-platform/verify.env` already holds the S3 keys from V-12/V-13.
3. `make terraform-plan-hcloud`, read the plan (2 servers, 1 network, 1 subnet, 1 firewall,
   1 ssh key, 1 volume, 1 S3 bucket + versioning + lock configuration, 1 OCI bucket).
4. `terraform apply <planfile>` (Level 3). Then `terraform output demo_cluster_url` and
   `ssh root@<server> cat /var/lib/rancher/k3s/server/tls/server-ca.crt` give the two public
   values the deploy workflow needs (`DEMO_CLUSTER_URL`, `DEMO_CLUSTER_CA`, Task 5.9).
5. Deletion of servers is `terraform destroy` (Level 3). **Buckets are never deleted by
   Terraform** (`lifecycle { prevent_destroy }` is deliberately not used because it would also
   block `destroy` of everything else; the bucket resources are simply left out of any destroy
   by `-target`, and Object Lock / the retention rule would refuse object deletion anyway).

## What the k3s node gets (ADR-035 §2)

`/etc/rancher/k3s/config.yaml` (Traefik and servicelb disabled, secrets encryption, private
network binding, `authentication-config`), `/etc/rancher/k3s/authn.yaml` (V-14: GitHub Actions
issuer, audience `energy-platform-demo`, `anonymous.enabled: false` explicit), the namespace
`energy-platform` with `pod-security.kubernetes.io/enforce: restricted`, a `Role` +
`RoleBinding` for `gha:<owner>/<repo>`. The Postgres volume is mounted under the k3s local-path
provisioner root once it is attached (device found by glob after boot). The public address is
added to `tls-san` through a `config.yaml.d` drop-in from the metadata service.

## API port exposure (ADR-035 §4)

`deploy_from_github_actions = true` (demo default) opens 6443 to the internet because
GitHub-hosted runner prefixes cannot be allow-listed; anonymous authentication is off and the
only identities are the admin client certificate and namespace-scoped OIDC tokens. Set it to
`false` for admin-only access (a self-hosted runner in the private network is the production
hardening step).
