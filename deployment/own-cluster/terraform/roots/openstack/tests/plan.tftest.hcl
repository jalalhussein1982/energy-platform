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
