output "server_id" {
  value = openstack_compute_instance_v2.server.id
}

output "server_public_address" {
  value = var.floating_ip
}

output "server_private_address" {
  value = local.server_private_ip
}

output "agent_ids" {
  value = openstack_compute_instance_v2.agent[*].id
}

output "k3s_token" {
  value     = random_password.k3s_token.result
  sensitive = true
}

output "authn_yaml" {
  value = local.authn_yaml
}

output "server_type" {
  value = var.server_type
}

output "node_count" {
  value = 1 + var.agent_count
}
