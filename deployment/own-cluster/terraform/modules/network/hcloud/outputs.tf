output "network_id" {
  value = hcloud_network.this.id
}

output "subnet_id" {
  value = hcloud_network_subnet.nodes.id
}

output "subnet_cidr" {
  value = var.subnet_cidr
}

output "private_iface" {
  description = "Interface name k3s binds flannel to on Hetzner private networks."
  value       = "enp7s0"
}
