# nodes/hcloud — one k3s server + N agents from the shared cloud-init templates (ADR-035 §1-§3).
# Contract shared with nodes/openstack: inputs {name, server_type, agent_count, image,
# k3s_version, network_id, subnet_cidr, private_iface, cluster_cidr, service_cidr,
# oidc_audience, github_repository, namespace, ssh_public_key, location, firewall_ids,
# storage_device}; outputs {server_public_address, server_private_address, agent_ids, k3s_token,
# authn_yaml, server_type, node_count}.
terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
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

resource "hcloud_ssh_key" "admin" {
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
    public_ip_metadata_url = "http://169.254.169.254/hetzner/v1/metadata/public-ipv4"
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

resource "hcloud_server" "server" {
  name         = "${var.name}-server"
  server_type  = var.server_type
  image        = var.image
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.admin.id]
  firewall_ids = var.firewall_ids

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  network {
    network_id = var.network_id
    ip         = local.server_private_ip
  }

  user_data = local.server_user_data

  labels = {
    role      = "server"
    residency = "DE"
  }
}

resource "hcloud_server" "agent" {
  count        = var.agent_count
  name         = "${var.name}-agent-${count.index + 1}"
  server_type  = var.server_type
  image        = var.image
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.admin.id]
  firewall_ids = var.firewall_ids

  public_net {
    ipv4_enabled = true
    ipv6_enabled = false
  }

  network {
    network_id = var.network_id
    ip         = cidrhost(var.subnet_cidr, 20 + count.index)
  }

  user_data = templatefile("${path.module}/../../../cloud-init/k3s-agent.yaml.tftpl", {
    server_private_address = local.server_private_ip
    private_address        = cidrhost(var.subnet_cidr, 20 + count.index)
    private_iface          = var.private_iface
    k3s_token              = random_password.k3s_token.result
    k3s_version            = var.k3s_version
  })

  labels = {
    role      = "agent"
    residency = "DE"
  }

  depends_on = [hcloud_server.server]
}
