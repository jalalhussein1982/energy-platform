output "volume_device" {
  value = openstack_compute_volume_attach_v2.postgres.device
}

output "bucket_a" {
  value = aws_s3_bucket.bronze.bucket
}

output "bucket_b" {
  value = openstack_objectstorage_container_v1.replica.name
}

output "lock_mode" {
  value = one(one(aws_s3_bucket_object_lock_configuration.bronze.rule).default_retention).mode
}

output "lock_days" {
  value = one(one(aws_s3_bucket_object_lock_configuration.bronze.rule).default_retention).days
}

output "replica_retention_days" {
  description = "Swift has no retention rule; the compensating control is ADR-021 (copy-verify, never overwrite)."
  value       = 0
}

output "replica_versioning" {
  value = "Disabled"
}
