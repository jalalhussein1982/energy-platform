# Mock-provider tests for the reference root (never applied, ADR-028). Proves the V-5 sizing,
# the V-14 authentication file, the V-6 store-A control and the admin-only API default.

mock_provider "openstack" {}
mock_provider "aws" {}

variables {
  application_credential_id     = "mock"
  application_credential_secret = "mock"
  admin_cidr                    = "203.0.113.5/32"
  ssh_public_key                = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMockKeyForTerraformTestOnly0000000000000 test"
  github_repository             = "jalalhussein1982/energy-platform"
  rgw_access_key                = "mock"
  rgw_secret_key                = "mock"
}

run "reference_sizing_and_controls" {
  command = plan

  assert {
    condition     = output.server_type == "e1.large" && output.node_count == 3
    error_message = "V-5 quota: 3 × e1.large (12 vCPU / 24 GB of 20 / 50 GB)"
  }

  assert {
    condition     = strcontains(output.authn_yaml, "anonymous:\n  enabled: false")
    error_message = "V-14: anonymous authentication explicitly off"
  }

  assert {
    condition     = output.lock_mode == "COMPLIANCE" && output.lock_days == 90
    error_message = "V-6: Object Lock on the reference RGW"
  }

  assert {
    condition     = output.replica_retention_days == 0
    error_message = "Swift has no retention rule; ADR-021 compensating control (documented, not faked)"
  }

  assert {
    condition     = output.api_allowed_cidrs == tolist([var.admin_cidr])
    error_message = "reference root defaults to admin-only API access"
  }

  assert {
    condition     = output.firewall_rules["22"] == tolist([var.admin_cidr])
    error_message = "SSH only from the author"
  }
}

run "quota_guard" {
  command = plan

  variables {
    agent_count = 3
  }

  expect_failures = [var.agent_count]
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
    condition     = yamldecode(one([for f in yamldecode(nonsensitive(output.server_cloud_init)).write_files : f.content if f.path == "/etc/rancher/k3s/authn.yaml"])).anonymous.enabled == false
    error_message = "the authn.yaml embedded in cloud-init must decode intact, anonymous auth off"
  }

  assert {
    condition     = strcontains(one([for f in yamldecode(nonsensitive(output.server_cloud_init)).write_files : f.content if endswith(f.path, "energy-platform-rbac.yaml")]), "kind: RoleBinding")
    error_message = "the namespace RBAC manifest must be embedded in cloud-init"
  }

  assert {
    condition     = strcontains(one([for f in yamldecode(nonsensitive(output.server_cloud_init)).write_files : f.content if endswith(f.path, "energy-platform-rbac.yaml")]), "resources: [replicasets, controllerrevisions]")
    error_message = "the deployer Role must let helm --wait read ReplicaSets and ControllerRevisions (first demo deploy, 2026-09-23)"
  }

  assert {
    condition = anytrue([
      for c in yamldecode(nonsensitive(output.server_cloud_init)).runcmd :
      startswith(c, "netplan apply;") && strcontains(c, "exit 1")
    ]) && anytrue([for f in yamldecode(nonsensitive(output.server_cloud_init)).write_files : f.path == "/etc/netplan/60-private-network.yaml"])
    error_message = "the private interface is configured by netplan and its address awaited before k3s (a late network attach left it DOWN, 2026-09-23)"
  }
}
