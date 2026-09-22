variable "name" {
  type = string
}

variable "server_type" {
  type        = string
  description = "Flavor; e1.large (4 vCPU / 8 GB) is the largest on the reference cloud (V-5)."
  default     = "e1.large"
}

variable "agent_count" {
  type    = number
  default = 2
}

variable "image" {
  type    = string
  default = "ubuntu-24.04-x86_64"
}

variable "location" {
  type    = string
  default = "brno1"
}

variable "k3s_version" {
  type    = string
  default = "v1.36.4+k3s1"
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
  default = "energy-platform-reference"
}

variable "github_repository" {
  type = string
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

variable "floating_ip" {
  type        = string
  description = "The one floating IP (V-5 quota), associated with the server."
}

variable "storage_device_glob" {
  type        = string
  description = "Cinder volumes appear as virtio-<id prefix>; verify on the reference cloud before any apply (never applied here)."
  default     = "/dev/disk/by-id/virtio-*"
}
