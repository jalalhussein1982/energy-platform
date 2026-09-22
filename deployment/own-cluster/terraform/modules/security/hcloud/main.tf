# security/hcloud — the firewall (ADR-035 §4): 443/tcp from anywhere (future ingress flag),
# 6443/tcp from var.api_allowed_cidrs (author CIDR, plus 0.0.0.0/0 when deploying from
# GitHub-hosted runners — anonymous auth is off, OIDC + RBAC are the control), 22/tcp from the
# admin CIDR only. Everything else inbound is denied; private-network traffic is not filtered
# by Hetzner cloud firewalls.
terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
  }
}

resource "hcloud_firewall" "nodes" {
  name = var.name

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
    description = "ingress (behind a values flag; nothing listens by default)"
  }

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "6443"
    source_ips  = var.api_allowed_cidrs
    description = "Kubernetes API (ADR-035 §4)"
  }

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = [var.admin_cidr]
    description = "SSH, author only"
  }

  rule {
    direction   = "in"
    protocol    = "icmp"
    source_ips  = [var.admin_cidr]
    description = "ping from the author"
  }
}
