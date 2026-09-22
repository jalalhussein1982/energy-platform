# roots/openstack — the reference cloud (MetaCentrum Brno1, V-5): mock-tested in CI, NEVER
# applied (ADR-028: no scheduled workload, release or bucket of ours on the reference
# environment). Sized to the verified quota: ≤ 3 × e1.large, one pre-provisioned network
# (routers=0), one floating IP. Auth = application credential (never a user password, V-5).

module "network" {
  source           = "../../modules/network/openstack"
  name             = var.project_network
  subnet_cidr      = var.subnet_cidr
  floating_ip_pool = var.floating_ip_pool
}

module "security" {
  source            = "../../modules/security/openstack"
  name              = var.name
  admin_cidr        = var.admin_cidr
  api_allowed_cidrs = local.api_allowed_cidrs
  subnet_cidr       = module.network.subnet_cidr
}

module "nodes" {
  source            = "../../modules/nodes/openstack"
  name              = var.name
  server_type       = var.server_type
  agent_count       = var.agent_count
  k3s_version       = var.k3s_version
  network_id        = module.network.network_id
  subnet_cidr       = module.network.subnet_cidr
  private_iface     = module.network.private_iface
  oidc_audience     = var.oidc_audience
  github_repository = var.github_repository
  namespace         = var.namespace
  ssh_public_key    = var.ssh_public_key
  firewall_ids      = [module.security.firewall_id]
  floating_ip       = module.network.floating_ip
}

module "storage" {
  source      = "../../modules/storage/openstack"
  name        = var.name
  server_id   = module.nodes.server_id
  volume_size = var.postgres_volume_size
  bucket_a    = var.bucket_a
  bucket_b    = var.bucket_b
  lock_days   = var.bronze_lock_days
}

locals {
  api_allowed_cidrs = var.deploy_from_github_actions ? [var.admin_cidr, "0.0.0.0/0"] : [var.admin_cidr]
}
