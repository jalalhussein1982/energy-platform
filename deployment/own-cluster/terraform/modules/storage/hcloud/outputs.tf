output "volume_device" {
  value = hcloud_volume.postgres.linux_device
}

output "bucket_a" {
  value = aws_s3_bucket.bronze.bucket
}

output "bucket_b" {
  value = oci_objectstorage_bucket.replica.name
}

output "lock_mode" {
  value = one(one(aws_s3_bucket_object_lock_configuration.bronze.rule).default_retention).mode
}

output "lock_days" {
  value = one(one(aws_s3_bucket_object_lock_configuration.bronze.rule).default_retention).days
}

output "replica_retention_days" {
  value = tonumber(one(one(oci_objectstorage_bucket.replica.retention_rules).duration).time_amount)
}

output "replica_versioning" {
  value = oci_objectstorage_bucket.replica.versioning
}
