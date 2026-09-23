# Mock-provider tests (ADR-001 amend rule 5, ADR-035 §3): no credentials, no network calls to
# a cloud. What they prove: the demo sizing (cx23, two nodes), the V-14 authentication file
# (anonymous auth explicitly off), the V-12/V-13 bucket controls (Object Lock COMPLIANCE on A,
# retention rule and versioning Disabled on B), and the ADR-035 §4 firewall shape.

# hcloud ids are numbers; the mock provider would generate strings, so computed ids get
# numeric defaults here (the values are meaningless, the types are not).
mock_provider "hcloud" {
  mock_resource "hcloud_network" {
    defaults = { id = 100 }
  }
  mock_resource "hcloud_network_subnet" {
    defaults = { id = "100-10.10.1.0/24" }
  }
  mock_resource "hcloud_firewall" {
    defaults = { id = 200 }
  }
  mock_resource "hcloud_ssh_key" {
    defaults = { id = 300 }
  }
  mock_resource "hcloud_server" {
    defaults = { id = 400, ipv4_address = "203.0.113.10" }
  }
  mock_resource "hcloud_volume" {
    defaults = { id = 500, linux_device = "/dev/disk/by-id/scsi-0HC_Volume_500" }
  }
}
mock_provider "aws" {}
mock_provider "oci" {}

variables {
  hcloud_token          = "mock"
  admin_cidr            = "203.0.113.5/32"
  ssh_public_key        = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMockKeyForTerraformTestOnly0000000000000 test"
  github_repository     = "jalalhussein1982/energy-platform"
  hetzner_s3_access_key = "mock"
  hetzner_s3_secret_key = "mock"
  oci_compartment_id    = "ocid1.compartment.oc1..mock"
  oci_namespace         = "mocknamespace"
}

run "demo_sizing_and_controls" {
  command = plan

  assert {
    condition     = output.server_type == "cx23"
    error_message = "ADR-028/ADR-035: the demo server type is cx23 (cx22 no longer exists, V-14)"
  }

  assert {
    condition     = output.node_count == 2
    error_message = "ADR-028: two nodes"
  }

  assert {
    condition     = strcontains(output.authn_yaml, "anonymous:\n  enabled: false")
    error_message = "V-14: anonymous authentication must be set off explicitly"
  }

  assert {
    condition     = strcontains(output.authn_yaml, "https://token.actions.githubusercontent.com") && strcontains(output.authn_yaml, "energy-platform-demo")
    error_message = "ADR-015 federation clause: GitHub Actions issuer and the audience"
  }

  assert {
    condition     = strcontains(output.authn_yaml, "claims.repository == 'jalalhussein1982/energy-platform'") && strcontains(output.authn_yaml, "refs/heads/main")
    error_message = "V-14 claim rules on repository and ref"
  }

  assert {
    condition     = output.lock_mode == "COMPLIANCE" && output.lock_days == 90
    error_message = "V-12: Object Lock COMPLIANCE is the store-A control"
  }

  assert {
    condition     = output.replica_versioning == "Disabled" && output.replica_retention_days == 90
    error_message = "V-13: store B = retention rule with versioning off (mutually exclusive)"
  }

  assert {
    condition     = contains(output.api_allowed_cidrs, "0.0.0.0/0") && contains(output.api_allowed_cidrs, var.admin_cidr)
    error_message = "ADR-035 §4: with deploy_from_github_actions the API port is open, anonymous auth off"
  }

  assert {
    condition     = output.firewall_rules["22"] == tolist([var.admin_cidr])
    error_message = "SSH only from the author's address"
  }

  assert {
    condition     = output.firewall_rules["443"] == sort(["0.0.0.0/0", "::/0"])
    error_message = "443 open for the ingress flag"
  }
}

run "admin_only_api" {
  command = plan

  variables {
    deploy_from_github_actions = false
  }

  assert {
    condition     = output.api_allowed_cidrs == tolist([var.admin_cidr])
    error_message = "ADR-028 §2 original shape: 6443 from the author's address only"
  }
}

# The k3s token is a random_password, unknown at plan time: this run applies against the mock
# providers (no cloud call; random generates locally) so the rendered cloud-init is known and can
# be parsed the way cloud-init will parse it on the node.
run "cloud_init_is_valid_yaml" {
  command = apply

  assert {
    condition     = can(yamldecode(nonsensitive(output.server_cloud_init)))
    error_message = "the rendered server cloud-init must be valid YAML (2026-09-23: an unindented embed made cloud-init drop the whole document and the demo nodes booted without k3s)"
  }

  assert {
    condition     = yamldecode(yamldecode(nonsensitive(output.server_cloud_init)).write_files[1].content).anonymous.enabled == false
    error_message = "the authn.yaml embedded in cloud-init must decode intact, anonymous auth off"
  }

  assert {
    condition     = strcontains(yamldecode(nonsensitive(output.server_cloud_init)).write_files[2].content, "kind: RoleBinding")
    error_message = "the namespace RBAC manifest must be embedded in cloud-init"
  }

  assert {
    condition = anytrue([
      for c in yamldecode(nonsensitive(output.server_cloud_init)).runcmd :
      strcontains(c, "mountpoint -q /var/lib/rancher/k3s/storage") && !strcontains(c, "LABEL=")
    ])
    error_message = "the Postgres volume is mounted by its by-id path and checked before k3s is installed (a pre-formatted volume has no label)"
  }
}
