# storage/openstack — a Cinder volume for Postgres, bucket A on the reference RGW (S3, Object
# Lock verified in V-6) over the aws provider, bucket B a Swift container on the second, independently
# operated endpoint (V-6). Same contract as storage/hcloud; mock-tested only (ADR-028: no bucket of
# ours is created on the reference environment).
terraform {
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "openstack_blockstorage_volume_v3" "postgres" {
  name = "${var.name}-postgres"
  size = var.volume_size
}

resource "openstack_compute_volume_attach_v2" "postgres" {
  instance_id = var.server_id
  volume_id   = openstack_blockstorage_volume_v3.postgres.id
}

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

resource "openstack_objectstorage_container_v1" "replica" {
  name   = var.bucket_b
  region = var.swift_region
  metadata = {
    "role"      = "bronze-replica"
    "residency" = "CZ"
  }
}
