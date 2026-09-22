variable "name" {
  type = string
}

variable "admin_cidr" {
  type        = string
  description = "The author's address (SSH, ping)."
}

variable "api_allowed_cidrs" {
  type        = list(string)
  description = "Who may reach 6443 (ADR-035 §4)."
}
