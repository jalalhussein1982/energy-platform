variable "name" {
  type    = string
  default = "energy-platform-demo"
}

variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "location" {
  type    = string
  default = "nbg1"
}

variable "network_zone" {
  type    = string
  default = "eu-central"
}

variable "server_type" {
  type    = string
  default = "cx23"
}

variable "agent_count" {
  type    = number
  default = 1
}

variable "k3s_version" {
  type    = string
  default = "v1.36.4+k3s1"
}

variable "admin_cidr" {
  type        = string
  description = "The author's address, /32."
}

variable "deploy_from_github_actions" {
  type        = bool
  description = "ADR-035 §4: open 6443 to the internet for GitHub-hosted runners (OIDC + RBAC are the control)."
  default     = true
}

variable "ssh_public_key" {
  type = string
}

variable "github_repository" {
  type        = string
  description = "owner/repo whose main branch may deploy (V-14 claim rule)."
}

variable "oidc_audience" {
  type    = string
  default = "energy-platform-demo"
}

variable "namespace" {
  type    = string
  default = "energy-platform"
}

variable "postgres_volume_size" {
  type    = number
  default = 10
}

variable "bucket_a" {
  type    = string
  default = "energy-platform-bronze"
}

variable "bucket_b" {
  type    = string
  default = "energy-platform-bronze-replica"
}

variable "bronze_lock_days" {
  type    = number
  default = 90
}

variable "replica_retention_days" {
  type    = number
  default = 90
}

variable "hetzner_s3_endpoint" {
  type    = string
  default = "https://nbg1.your-objectstorage.com"
}

variable "hetzner_s3_region" {
  type    = string
  default = "nbg1"
}

variable "hetzner_s3_access_key" {
  type      = string
  sensitive = true
}

variable "hetzner_s3_secret_key" {
  type      = string
  sensitive = true
}

variable "oci_config_profile" {
  type    = string
  default = "DEFAULT"
}

variable "oci_region" {
  type    = string
  default = "eu-frankfurt-1"
}

variable "oci_compartment_id" {
  type = string
}

variable "oci_namespace" {
  type        = string
  description = "Object Storage namespace (`oci os ns get`)."
}
