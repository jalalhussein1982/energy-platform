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
`test`/`mock_provider` features). **A saved plan is applied by the tool that made it**: a
Terraform plan is unreadable to `tofu` and the reverse ("string field contains invalid UTF-8"),
and `apply` checks the lock file the plan was made with. Since 2026-09-23 the author's Mac has
Terraform 1.16.3, so `make` picks `terraform`; the committed `.terraform.lock.hcl` files are
Terraform's (both roots validate and pass their mock tests under Terraform 1.16.3 and OpenTofu
1.12.6).

## Cost guard (ADR-028 §5) — before the first `apply`

| Account | Ceiling | What runs | Estimate (2026-09) |
|---|---|---|---|
| Hetzner Cloud | **€25 / month** budget alert in the console | 2 × `cx23` (≈ €3.79 each), one 10 GB volume (≈ €0.50), one primary IPv4 (≈ €0.60), Object Storage (≈ €5 base incl. 1 TB, at demo volume) | ≈ €14 / month |
| OCI | **€10 / month** budget alert in the console | Object Storage store B within the Always Free 20 GB; egress within the free allowance at demo volume | ≈ €0 / month |

Everything written to either bucket is locked for 90 days (Object Lock on A, retention rule on
B) and cannot be deleted early, so what the demo writes per day is the real cost driver. With
ADR-036 amendment 1 (2026-09-23) that is Bronze plus one compressed base backup a day plus
compressed WAL — tens of MB a day at demo volume (docs/07 §5.2); the first shape (raw WAL,
96 bases a day, ≈ 4.5 GiB/day) was fixed before any apply.

**Hetzner budget: a console check, not automation (Phase 9, G16).** Hetzner Cloud has no
budget API or CLI (checked 2026-09-23; the OCI side has a real budget with a €10 forecast rule
and the author's €1 `zero-spend-guard`). What the author checks in the Hetzner Console, project
`energy-platform`:

1. **Servers:** exactly `energy-platform-demo-server` and `energy-platform-demo-agent-1`
   (`cx23`). No `ep-cleanclone-*` or `energy-platform-v14` left over (throwaways are deleted
   after use).
2. **Volumes / Primary IPs / Networks / Firewalls:** one 10 GB volume, the servers' primary
   IPs, one network, one firewall. Nothing unattached.
3. **Object Storage:** bucket `energy-platform-bronze` (and the author's own bucket).
   Usage in the tens of MB a day (`docs/07` §5.2).
4. **Billing → usage for the current month:** on track for about €14. If the account offers a
   usage or cost notification, set it at €25; otherwise this check is the control, done weekly
   while the demo runs.

Author checklist, in this order:

1. Create the budget alerts in both consoles at the ceilings above.
2. Export the variables the root needs (never commit them): `TF_VAR_hcloud_token`,
   `TF_VAR_hetzner_s3_access_key`, `TF_VAR_hetzner_s3_secret_key`, `TF_VAR_admin_cidr`,
   `TF_VAR_ssh_public_key`, `TF_VAR_github_repository`, `TF_VAR_oci_compartment_id`,
   `TF_VAR_oci_namespace`; the OCI provider reads `~/.oci/config` (`oci_config_profile`).
   `~/.config/energy-platform/verify.env` already holds the S3 keys from V-12/V-13.
3. `make terraform-plan-hcloud`, read the plan (2 servers, 1 network, 1 subnet, 1 firewall,
   1 ssh key, 1 volume, 1 S3 bucket + versioning + lock configuration, 1 OCI bucket).
   *(2026-09-23: planned by the agent with Terraform 1.16.3 — `hcloud-20260923-011113.tfplan`,
   12 to add, `github_repository = jalalhussein1982/energy-platform`, admin `/32` = the
   author's address at 01:11 CEST; the 2026-09-22 plan was deleted.)*
4. Immediately before applying, check the admin address still matches: `curl -4 -s
   https://api.ipify.org` against `terraform -chdir=… show -json <planfile> | jq -r
   .variables.admin_cidr.value`. A different address only locks SSH out (the API port is open
   to OIDC tokens, ADR-035 §4), but step 5 needs SSH — re-plan if it changed. Then
   `terraform -chdir=deployment/own-cluster/terraform/roots/hcloud apply <planfile>` (Level 3).
5. `terraform output demo_cluster_url` and
   `ssh root@<server> cat /var/lib/rancher/k3s/server/tls/server-ca.crt` give the two public
   values the deploy workflow needs (`DEMO_CLUSTER_URL`, `DEMO_CLUSTER_CA`, Task 5.9).
   The state is local (`roots/hcloud/terraform.tfstate`, git-ignored): it is the only record of
   what exists, `destroy` needs it, and it holds the k3s token and S3 keys in plain text — keep a
   `chmod 600` copy outside the checkout.
   *(2026-09-23: applied; the first apply exposed five defects in the node bootstrap and the
   Role, fixed and tested — `docs/07-operations.md` §4.1.)* Replacing the server re-creates the
   k3s CA: replace the agent in the same apply (`-replace='module.nodes.hcloud_server.agent[0]'`)
   and redo `DEMO_CLUSTER_CA`, the admin kubeconfig and the namespace Secrets. With Postgres data
   on the volume, a server replacement also needs the restore procedure (docs/07 §5).
6. Deletion of servers is `terraform destroy` (Level 3). **Buckets are never deleted by
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

## Two author-run repairs prepared 2026-09-24

Both were prepared by the maintainer agent and left unapplied on purpose: its permission
classifier refuses production database access and SSH to the nodes, which matches the authority
table in `CLAUDE.md`. Each is one command.

**1. Node-level metadata block** (threat-model residual: k3s system pods carry no NetworkPolicy
and `169.254.169.254` serves the node's `user_data`, join token included). From the checkout,
with the admin SSH key and the `hcloud` state present:

```bash
make demo-metadata-block                    # server, then the agent through the server (ProxyJump)
make demo-metadata-verify KUBECONFIG=~/.kube/energy-platform-demo.yaml   # PASS = the probe times out
```

What it installs is `node-metadata-block.sh`: a `raw` PREROUTING rule dropping `10.42.0.0/16 →
169.254.169.254`, kept by a oneshot systemd unit ordered before k3s. Removal on a node:
`systemctl disable --now energy-platform-metadata-block`. The agent's private address is
`cidrhost(subnet, 20)` = `10.10.1.20` (`DEMO_AGENT_PRIVATE` if the subnet ever changes). A new
node built from cloud-init does **not** get the rule automatically — re-run the target after any
node replacement (cloud-init is first boot only, and this rule was deliberately kept out of the
nodes module's templates until it has been exercised on a live node).

**2. The 672 wrong T2 rows of 22 September** (`docs/07` §4.3): `repairs/2026-09-22-t2-wrong-day.sql`,
one transaction, aborts unless exactly 672 rows match. Run command in the file header. Then never
`replay` the 22 September runs of `ote_intraday_market_xlsx`.
