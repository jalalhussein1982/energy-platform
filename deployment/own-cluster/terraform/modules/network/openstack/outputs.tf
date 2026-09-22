output "network_id" {
  value = data.openstack_networking_network_v2.project.id
}

output "subnet_id" {
  value = data.openstack_networking_subnet_v2.nodes.id
}

output "subnet_cidr" {
  value = var.subnet_cidr
}

output "private_iface" {
  value = "ens3"
}

output "floating_ip" {
  value = openstack_networking_floatingip_v2.ingress.address
}
