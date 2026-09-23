# nodes/openstack — one k3s server + N agents on the reference cloud, sized to the V-5 quota
# (≤ 3 × e1.large = 12 vCPU / 24 GB of 20 / 50 GB). Same contract and cloud-init as nodes/hcloud.
terraform {
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

resource "random_password" "k3s_token" {
  length  = 48
  special = false
}

resource "openstack_compute_keypair_v2" "admin" {
  name       = "${var.name}-admin"
  public_key = var.ssh_public_key
}

locals {
  server_private_ip = cidrhost(var.subnet_cidr, 10)
  authn_yaml = templatefile("${path.module}/../../../cloud-init/authn.yaml.tftpl", {
    oidc_audience     = var.oidc_audience
    github_repository = var.github_repository
  })
  rbac_yaml = templatefile("${path.module}/../../../cloud-init/rbac.yaml.tftpl", {
    namespace         = var.namespace
    github_repository = var.github_repository
  })
  # rendered once: the server's user_data and the server_user_data output the mock tests parse
  server_user_data = templatefile("${path.module}/../../../cloud-init/k3s-server.yaml.tftpl", {
    public_ip_metadata_url = "http://169.254.169.254/latest/meta-data/public-ipv4"
    private_address        = local.server_private_ip
    private_iface          = var.private_iface
    cluster_cidr           = var.cluster_cidr
    service_cidr           = var.service_cidr
    k3s_token              = random_password.k3s_token.result
    k3s_version            = var.k3s_version
    authn_yaml             = local.authn_yaml
    rbac_yaml              = local.rbac_yaml
    storage_device_glob    = var.storage_device_glob
  })
}

resource "openstack_compute_instance_v2" "server" {
  name            = "${var.name}-server"
  flavor_name     = var.server_type
  image_name      = var.image
  key_pair        = openstack_compute_keypair_v2.admin.name
  security_groups = var.firewall_ids

  network {
    uuid        = var.network_id
    fixed_ip_v4 = local.server_private_ip
  }

  user_data = local.server_user_data

  # ADR-035 amendment 1: cloud-init is first boot only. The provider keeps a hash of user_data,
  # so a template change would REPLACE the node (new k3s CA and datastore on the server); later
  # changes to authn.yaml / the RBAC manifest go over SSH (`make demo-reconfigure`).
  lifecycle {
    ignore_changes = [user_data]
  }

  metadata = {
    role      = "server"
    residency = "CZ"
  }
}

resource "openstack_compute_instance_v2" "agent" {
  count           = var.agent_count
  name            = "${var.name}-agent-${count.index + 1}"
  flavor_name     = var.server_type
  image_name      = var.image
  key_pair        = openstack_compute_keypair_v2.admin.name
  security_groups = var.firewall_ids

  network {
    uuid        = var.network_id
    fixed_ip_v4 = cidrhost(var.subnet_cidr, 20 + count.index)
  }

  user_data = templatefile("${path.module}/../../../cloud-init/k3s-agent.yaml.tftpl", {
    server_private_address = local.server_private_ip
    private_address        = cidrhost(var.subnet_cidr, 20 + count.index)
    private_iface          = var.private_iface
    k3s_token              = random_password.k3s_token.result
    k3s_version            = var.k3s_version
  })

  lifecycle {
    ignore_changes = [user_data] # ADR-035 amendment 1 (see the server)
  }

  metadata = {
    role      = "agent"
    residency = "CZ"
  }

  depends_on = [openstack_compute_instance_v2.server]
}

resource "openstack_networking_floatingip_associate_v2" "server" {
  floating_ip = var.floating_ip
  port_id     = openstack_compute_instance_v2.server.network[0].port
}
