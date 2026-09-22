variable "name" {
  type = string
}

variable "server_id" {
  type = string
}

variable "volume_size" {
  type    = number
  default = 10
}

variable "bucket_a" {
  type = string
}

variable "bucket_b" {
  type = string
}

variable "lock_days" {
  type        = number
  description = "Object Lock COMPLIANCE default retention on store A."
  default     = 90
}

variable "retention_days" {
  type        = number
  description = "OCI retention rule on store B."
  default     = 90
}

variable "oci_compartment_id" {
  type = string
}

variable "oci_namespace" {
  type = string
}
