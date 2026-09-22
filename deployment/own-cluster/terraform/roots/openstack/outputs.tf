output "server_public_address" {
  value = module.nodes.server_public_address
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
