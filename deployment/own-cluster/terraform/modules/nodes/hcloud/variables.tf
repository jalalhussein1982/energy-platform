variable "name" {
  type = string
}

variable "server_type" {
  type        = string
  description = "cx23 (V-14: cx22 no longer exists)."
  default     = "cx23"
}

variable "agent_count" {
  type    = number
  default = 1
}

variable "image" {
  type    = string
  default = "ubuntu-24.04"
}

variable "location" {
  type    = string
  default = "nbg1"
}

variable "k3s_version" {
  type        = string
  description = "Pinned k3s release (V-14 verified v1.36.4+k3s1)."
  default     = "v1.36.4+k3s1"
}

variable "network_id" {
  type = string
}

variable "subnet_cidr" {
  type = string
}

variable "private_iface" {
  type = string
}

variable "cluster_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "service_cidr" {
  type    = string
  default = "10.43.0.0/16"
}

variable "oidc_audience" {
  type    = string
  default = "energy-platform-demo"
}

variable "github_repository" {
  type        = string
  description = "owner/repo whose main branch may deploy (claim rule)."
}

variable "namespace" {
  type    = string
  default = "energy-platform"
}

variable "ssh_public_key" {
  type = string
}

variable "firewall_ids" {
  type    = list(string)
  default = []
}

variable "storage_device_glob" {
  type        = string
  description = "Glob matching the Postgres volume's device on the server (Hetzner: scsi-0HC_Volume_*); \"\" = none."
  default     = "/dev/disk/by-id/scsi-0HC_Volume_*"
}
