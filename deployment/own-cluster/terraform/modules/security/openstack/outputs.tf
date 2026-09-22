output "firewall_id" {
  value = openstack_networking_secgroup_v2.nodes.id
}

output "rules" {
  value = {
    "443"  = sort(["0.0.0.0/0"])
    "6443" = sort([for c in var.api_allowed_cidrs : c if !strcontains(c, ":")])
    "22"   = sort([var.admin_cidr])
  }
}
