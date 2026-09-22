terraform {
  required_version = ">= 1.8.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# V-5: application credential, never a user password. Values come from CI secrets or the
# author's environment (OS_APPLICATION_CREDENTIAL_ID / _SECRET), never from the repository.
provider "openstack" {
  auth_url                      = var.auth_url
  region                        = var.region
  application_credential_id     = var.application_credential_id
  application_credential_secret = var.application_credential_secret
}

# The reference RGW (V-6) speaks S3.
provider "aws" {
  region     = "us-east-1"
  access_key = var.rgw_access_key
  secret_key = var.rgw_secret_key

  skip_credentials_validation = true
  skip_region_validation      = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  s3_use_path_style           = true

  endpoints {
    s3 = var.rgw_endpoint
  }
}
