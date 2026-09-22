terraform {
  required_version = ">= 1.8.0"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

# Hetzner Object Storage speaks S3; the aws provider is pointed at it and told not to expect AWS.
provider "aws" {
  region     = var.hetzner_s3_region
  access_key = var.hetzner_s3_access_key
  secret_key = var.hetzner_s3_secret_key

  skip_credentials_validation = true
  skip_region_validation      = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  s3_use_path_style           = true

  endpoints {
    s3 = var.hetzner_s3_endpoint
  }
}

# OCI: the author's ~/.oci/config profile (never keys in the repository or in CI).
provider "oci" {
  config_file_profile = var.oci_config_profile
  region              = var.oci_region
}
