# network/openstack — the reference cloud (MetaCentrum Brno1, V-5): routers=0, so the project
# network is pre-provisioned and consumed by name; one floating IP is the quota (single
# ingress VIP). Same contract as network/hcloud.
terraform {
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
  }
}

data "openstack_networking_network_v2" "project" {
  name = var.name
}

data "openstack_networking_subnet_v2" "nodes" {
  network_id = data.openstack_networking_network_v2.project.id
  cidr       = var.subnet_cidr
}

resource "openstack_networking_floatingip_v2" "ingress" {
  pool = var.floating_ip_pool
}
