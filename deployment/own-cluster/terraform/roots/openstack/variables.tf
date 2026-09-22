variable "name" {
  type    = string
  default = "energy-platform-ref"
}

variable "auth_url" {
  type    = string
  default = "https://identity.brno.openstack.cloud.e-infra.cz/v3"
}

variable "region" {
  type    = string
  default = "brno1"
}

variable "application_credential_id" {
  type      = string
  sensitive = true
}

variable "application_credential_secret" {
  type      = string
  sensitive = true
}

variable "project_network" {
  type        = string
  description = "The pre-provisioned project network (routers=0, V-5)."
  default     = "energy-platform-net"
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.1.0/24"
}

variable "floating_ip_pool" {
  type    = string
  default = "public-muni-147-251-115-PERSONAL"
}

variable "server_type" {
  type    = string
  default = "e1.large"
}

variable "agent_count" {
  type        = number
  description = "≤ 2 keeps the total at 3 × e1.large = 12 vCPU / 24 GB inside the 20 / 50 GB quota (V-5)."
  default     = 2
  validation {
    condition     = var.agent_count <= 2
    error_message = "V-5 quota: at most 3 e1.large nodes (server + 2 agents)."
  }
}

variable "k3s_version" {
  type    = string
  default = "v1.36.4+k3s1"
}

variable "admin_cidr" {
  type = string
}

variable "deploy_from_github_actions" {
  type    = bool
  default = false
}

variable "ssh_public_key" {
  type = string
}

variable "github_repository" {
  type = string
}

variable "oidc_audience" {
  type    = string
  default = "energy-platform-reference"
}

variable "namespace" {
  type    = string
  default = "energy-platform"
}

variable "postgres_volume_size" {
  type    = number
  default = 20
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

variable "rgw_endpoint" {
  type    = string
  default = "https://s3.cl4.du.cesnet.cz"
}

variable "rgw_access_key" {
  type      = string
  sensitive = true
}

variable "rgw_secret_key" {
  type      = string
  sensitive = true
}
