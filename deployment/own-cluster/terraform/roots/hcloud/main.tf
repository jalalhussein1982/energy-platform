# roots/hcloud — the demo environment (ADR-028, ADR-035): two cx23 nodes on Hetzner Cloud running
# k3s with GitHub-OIDC structured authentication, one private network, one firewall, one
# Postgres volume, bucket A on Hetzner Object Storage (Object Lock), bucket B on OCI (retention
# rule). Applied by the author only (`terraform apply` is Level 3); the agent runs
# `make terraform-plan-hcloud`, which writes the plan outside the repository.

module "network" {
  source = "../../modules/network/hcloud"
  name   = var.name
  zone   = var.network_zone
}

module "security" {
  source            = "../../modules/security/hcloud"
  name              = var.name
  admin_cidr        = var.admin_cidr
  api_allowed_cidrs = local.api_allowed_cidrs
}

module "nodes" {
  source              = "../../modules/nodes/hcloud"
  name                = var.name
  server_type         = var.server_type
  agent_count         = var.agent_count
  location            = var.location
  k3s_version         = var.k3s_version
  network_id          = module.network.network_id
  subnet_cidr         = module.network.subnet_cidr
  private_iface       = module.network.private_iface
  oidc_audience       = var.oidc_audience
  github_repository   = var.github_repository
  namespace           = var.namespace
  ssh_public_key      = var.ssh_public_key
  firewall_ids        = [module.security.firewall_id]
  storage_device_glob = "/dev/disk/by-id/scsi-0HC_Volume_*" # the volume attached by the storage module
}

module "storage" {
  source             = "../../modules/storage/hcloud"
  name               = var.name
  server_id          = module.nodes.server_id
  volume_size        = var.postgres_volume_size
  bucket_a           = var.bucket_a
  bucket_b           = var.bucket_b
  lock_days          = var.bronze_lock_days
  retention_days     = var.replica_retention_days
  oci_compartment_id = var.oci_compartment_id
  oci_namespace      = var.oci_namespace
}

locals {
  # ADR-035 §4: GitHub-hosted runners cannot be allow-listed by CIDR (thousands of prefixes),
  # so the API port opens to the internet when deploying from Actions; anonymous auth is off,
  # OIDC + namespace RBAC are the control. Set deploy_from_github_actions=false for admin-only.
  api_allowed_cidrs = var.deploy_from_github_actions ? [var.admin_cidr, "0.0.0.0/0", "::/0"] : [var.admin_cidr]
}
