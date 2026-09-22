output "firewall_id" {
  value = hcloud_firewall.nodes.id
}

output "rules" {
  description = "port -> source list, for the mock tests."
  value       = { for r in hcloud_firewall.nodes.rule : coalesce(r.port, r.protocol) => sort(r.source_ips) }
}
