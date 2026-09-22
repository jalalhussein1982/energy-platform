variable "name" {
  type = string
}

variable "server_id" {
  type = string
}

variable "volume_size" {
  type    = number
  default = 20
}

variable "bucket_a" {
  type = string
}

variable "bucket_b" {
  type = string
}

variable "lock_days" {
  type    = number
  default = 90
}

variable "retention_days" {
  type        = number
  description = "Kept for contract parity; Swift has no retention rule (the ADR-021 compensating control applies)."
  default     = 90
}

variable "swift_region" {
  type    = string
  default = "brno1"
}
