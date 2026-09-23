output "server_public_address" {
  value = module.nodes.server_public_address
}

output "server_private_address" {
  value = module.nodes.server_private_address
}

output "server_type" {
  value = module.nodes.server_type
}

output "node_count" {
  value = module.nodes.node_count
}

output "api_allowed_cidrs" {
  value = local.api_allowed_cidrs
}

output "firewall_rules" {
  value = module.security.rules
}

output "authn_yaml" {
  value = module.nodes.authn_yaml
}

output "server_cloud_init" {
  description = "The rendered server cloud-init, for the mock tests (holds the k3s token)."
  value       = module.nodes.server_user_data
  sensitive   = true
}

output "bucket_a" {
  value = module.storage.bucket_a
}

output "bucket_b" {
  value = module.storage.bucket_b
}

output "lock_mode" {
  value = module.storage.lock_mode
}

output "lock_days" {
  value = module.storage.lock_days
}

output "replica_retention_days" {
  value = module.storage.replica_retention_days
}

output "replica_versioning" {
  value = module.storage.replica_versioning
}

output "volume_device" {
  value = module.storage.volume_device
}

output "demo_cluster_url" {
  description = "DEMO_CLUSTER_URL repository variable for the OIDC deploy (Task 5.9)."
  value       = "https://${module.nodes.server_public_address}:6443"
}
