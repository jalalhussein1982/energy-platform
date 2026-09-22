variable "name" {
  type        = string
  description = "Name of the pre-provisioned project network (routers=0 on the reference cloud, V-5)."
}

variable "cidr" {
  type    = string
  default = "10.10.0.0/16"
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.1.0/24"
}

variable "zone" {
  type    = string
  default = "nova"
}

variable "floating_ip_pool" {
  type    = string
  default = "public-muni-147-251-115-PERSONAL"
}
