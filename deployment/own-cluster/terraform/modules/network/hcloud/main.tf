# network/hcloud — one private network + subnet (ADR-035 §3). Contract shared with
# network/openstack: inputs {name, cidr, subnet_cidr, zone}, outputs {network_id, subnet_id,
# subnet_cidr, private_iface}.
terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
  }
}

resource "hcloud_network" "this" {
  name     = var.name
  ip_range = var.cidr
}

resource "hcloud_network_subnet" "nodes" {
  network_id   = hcloud_network.this.id
  type         = "cloud"
  network_zone = var.zone
  ip_range     = var.subnet_cidr
}
