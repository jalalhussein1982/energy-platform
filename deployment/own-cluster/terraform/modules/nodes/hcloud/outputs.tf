output "server_id" {
  value = hcloud_server.server.id
}

output "server_public_address" {
  value = hcloud_server.server.ipv4_address
}

output "server_private_address" {
  value = local.server_private_ip
}

output "agent_ids" {
  value = hcloud_server.agent[*].id
}

output "k3s_token" {
  value     = random_password.k3s_token.result
  sensitive = true
}

output "rbac_yaml" {
  description = "The rendered namespace RBAC manifest (`make demo-reconfigure` pushes it; ADR-035 amendment 1)."
  value       = local.rbac_yaml
}

output "authn_yaml" {
  description = "The rendered AuthenticationConfiguration (mock tests assert anonymous.enabled: false)."
  value       = local.authn_yaml
}

output "server_type" {
  value = var.server_type
}

output "node_count" {
  value = 1 + var.agent_count
}

output "server_user_data" {
  description = "The rendered server cloud-init (the mock tests parse it; holds the k3s token)."
  value       = local.server_user_data
  sensitive   = true
}
