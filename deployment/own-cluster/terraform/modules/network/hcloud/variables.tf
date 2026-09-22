variable "name" {
  type        = string
  description = "Network name."
}

variable "cidr" {
  type        = string
  description = "Private network range."
  default     = "10.10.0.0/16"
}

variable "subnet_cidr" {
  type        = string
  description = "Subnet for the nodes."
  default     = "10.10.1.0/24"
}

variable "zone" {
  type        = string
  description = "Hetzner network zone (eu-central for nbg1/fsn1/hel1)."
  default     = "eu-central"
}
