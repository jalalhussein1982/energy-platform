# storage/hcloud — the Postgres block volume, bucket A on Hetzner Object Storage (versioning +
# Object Lock COMPLIANCE, V-12) over the aws provider pointed at the S3 endpoint, and bucket B
# on OCI Object Storage (retention rule, versioning Disabled, V-13) — ADR-036 §1.
# Contract shared with storage/openstack: inputs {name, server_id, volume_size, bucket_a,
# bucket_b, lock_days, retention_days, oci_compartment_id, oci_namespace}, outputs
# {volume_device, bucket_a, bucket_b, lock_mode, lock_days, replica_retention_days, replica_versioning}.
terraform {
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
  }
}

resource "hcloud_volume" "postgres" {
  name      = "${var.name}-postgres"
  size      = var.volume_size
  server_id = var.server_id
  format    = "ext4"
}

# ---- store A: Hetzner Object Storage (S3 API; hcloud has no bucket API, V-12)
resource "aws_s3_bucket" "bronze" {
  bucket              = var.bucket_a
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "bronze" {
  bucket = aws_s3_bucket.bronze.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "bronze" {
  bucket = aws_s3_bucket.bronze.id
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.lock_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.bronze]
}

# ---- store B: OCI Object Storage — retention rule; versioning must stay Disabled (V-13)
resource "oci_objectstorage_bucket" "replica" {
  compartment_id = var.oci_compartment_id
  namespace      = var.oci_namespace
  name           = var.bucket_b
  versioning     = "Disabled"
  access_type    = "NoPublicAccess"

  retention_rules {
    display_name = "bronze-replica-immutable"
    duration {
      time_amount = var.retention_days
      time_unit   = "DAYS"
    }
  }

  freeform_tags = {
    residency = "DE"
    role      = "bronze-replica"
  }
}
