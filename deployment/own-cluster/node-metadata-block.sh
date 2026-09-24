#!/bin/sh
# energy-platform — node-level drop of pod traffic to the cloud metadata service.
#
# Why (docs/threat-model.md, residual of the egress gate; docs/07 §4.2): the NetworkPolicies cover
# the platform's pods only. k3s's own system pods carry no policy, and 169.254.169.254 serves the
# node's user_data — the k3s join token included. This rule closes that path for every pod on the
# node, policy or not.
#
# How: one rule in the raw table's PREROUTING chain, which runs before conntrack and before any
# filter/FORWARD chain that flannel or kube-router install (flannel appends an ACCEPT for the pod
# CIDR to FORWARD, so a FORWARD rule could be shadowed; raw PREROUTING cannot). Packets from the
# pod CIDR arrive on cni0 (this node's pods) or flannel.1 (other nodes' pods) and are dropped
# before routing. Host traffic uses OUTPUT, so cloud-init's own metadata read at first boot and
# hostNetwork pods are unaffected — hostNetwork pods are k3s system components, not platform
# workloads (the chart never sets hostNetwork).
#
# Persistence: a oneshot systemd unit ordered before k3s, so the rule survives reboots and k3s
# restarts. Idempotent: re-running replaces the unit and re-checks the rule.
#
# Run on each node as root, from the checkout: `make demo-metadata-block` (server + agent over
# SSH, this file on stdin). Removal: `systemctl disable --now energy-platform-metadata-block`.
set -eu

POD_CIDR="${POD_CIDR:-10.42.0.0/16}"   # k3s cluster-cidr (cloud-init/k3s-server.yaml.tftpl)
META="169.254.169.254"
UNIT=/etc/systemd/system/energy-platform-metadata-block.service

IPT="$(command -v iptables || true)"
if [ -z "$IPT" ] && [ -x /var/lib/rancher/k3s/data/current/bin/iptables ]; then
  IPT=/var/lib/rancher/k3s/data/current/bin/iptables   # k3s ships one when the image has none
fi
if [ -z "$IPT" ]; then
  echo "metadata-block: no iptables binary on $(hostname)" >&2
  exit 1
fi

cat > "$UNIT" <<EOF
[Unit]
Description=energy-platform: drop pod traffic to the cloud metadata service (raw PREROUTING)
After=network-pre.target
Before=k3s.service k3s-agent.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c '$IPT -t raw -C PREROUTING -s $POD_CIDR -d $META -j DROP 2>/dev/null || $IPT -t raw -I PREROUTING 1 -s $POD_CIDR -d $META -j DROP'
ExecStop=/bin/sh -c '$IPT -t raw -D PREROUTING -s $POD_CIDR -d $META -j DROP 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now energy-platform-metadata-block.service >/dev/null 2>&1

if "$IPT" -t raw -C PREROUTING -s "$POD_CIDR" -d "$META" -j DROP; then
  echo "metadata-block: active on $(hostname) — $POD_CIDR -> $META dropped in raw PREROUTING ($IPT)"
else
  echo "metadata-block: rule missing on $(hostname) after enabling the unit" >&2
  exit 1
fi
