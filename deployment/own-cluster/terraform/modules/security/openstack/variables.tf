variable "name" {
  type = string
}

variable "admin_cidr" {
  type = string
}

variable "api_allowed_cidrs" {
  type = list(string)
}

variable "subnet_cidr" {
  type        = string
  description = "Node subnet: unrestricted between nodes (flannel VXLAN, kubelet)."
}
