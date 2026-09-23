# ADR-026 — Egress boundary: coarse NetworkPolicy plus host enforcement in the fetch layer

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | Codex review F08; amends ADR-008 "SSRF" mechanism and `03` Phase 5 "NetworkPolicies (egress per target allowlist)" |
| Supersedes | ADR-008 sentence "Kubernetes egress `NetworkPolicy` so a capture pod can reach only its declared hosts" |
| Amended | 2026-09-23, amendment 1 (below): a response-body cap in fetch; amendment 2: layer 1 is enforced only once a pod's policy is synced — an init-container gate on CNIs that apply it asynchronously |

## Context

The standard `NetworkPolicy` API selects pods, namespaces and IP blocks; it cannot express a
hostname, follow a redirect, or notice that an approved name resolved to a private address. It is
also only enforced when the CNI implements it. ADR-008 promised per-host egress from it. A
contributor-controlled `allowed_hosts` list is, in addition, not an independently approved
policy (F04/ADR-022).

## Decision

1. **Layer 1 — `NetworkPolicy` in the core chart (standard API, no CRD).** Default-deny egress
   for every platform pod. Allow: DNS (UDP/TCP 53 to kube-dns), Postgres, the object-store
   endpoints (namespace selector or `ipBlock` from values). **Capture and backfill pods only**
   additionally get TCP 443 to `0.0.0.0/0` **except** `10.0.0.0/8`, `172.16.0.0/12`,
   `192.168.0.0/16`, `169.254.0.0/16`, `100.64.0.0/10`, `127.0.0.0/8` and the cluster pod/service
   CIDRs from values. Process, gap-detector, tiering and hook pods have no internet egress. This
   layer's job is "no private/metadata destination, no non-443 port, no egress from pods that
   should never fetch"; it is not per-host.

2. **Layer 2 — host enforcement in `energy_platform.fetch`** (the only HTTP client, A-7):
   - scheme `https` only; `http` requires `allow_insecure: true` in the manifest **and** the same
     flag on the host's registry entry;
   - the host must be in the manifest's `allowed_hosts` **and** in the platform host registry
     (`energy_platform/contracts/hosts.py`, CODEOWNERS-protected; adding a host is Route B,
     ADR-022);
   - fetch resolves the name itself, rejects any resolved address in the ranges of layer 1, and
     re-checks the connected peer address after the connection is established (mismatch aborts);
   - redirects are not followed by the client; fetch follows them itself up to `max_redirects`
     (default 3) and validates every hop exactly as the first request; a hop to a host outside
     the allowlist fails the fetch with `redirect_to_unlisted_host`;
   - ports: 443 unless the registry entry allows another;
   - proxy variables (`HTTP_PROXY`/`NO_PROXY`, A-7) are honoured; the proxy address itself is
     validated against the registry once at start-up.

3. **Layer 3 — optional FQDN policy.** `egress.fqdnPolicy: none | cilium` renders a
   `CiliumNetworkPolicy` with `toFQDNs` from the union of registry hosts. Off by default; allowed
   only where the operator has verified the CNI. Never part of the core chart's requirements.

4. **Verification.**
   - Phase 3 negative tests (offline, fake transport): redirect to a private address, redirect to
     an unlisted host, host absent from the registry, `http` scheme, metadata address, port 8080.
   - Phase 5, local profile: kind with a policy-enforcing CNI (kindnet does not enforce
     `NetworkPolicy`; the local profile installs Calico or Cilium in policy-only mode) — a
     legitimate capture succeeds; a pod `curl` to `169.254.169.254` and to a private address is
     blocked; a process pod cannot reach the internet.
   - Tenant profile: new verification **V-11** — does the reference cluster's CNI enforce egress
     `NetworkPolicy`? (V-4 verified only that policies may be *created*.) Until CONFIRMED, layer 1
     is documented as "declared, enforcement unverified" for that profile, and layer 2 is the
     control that is known to hold.

## Rationale

Two controls with different jobs: the network layer stops classes of destination independently
of application bugs; the application layer knows hostnames, redirects and resolution. Neither
alone is the promise ADR-008 made; together they are, and the tenant chart still needs no CRD.

## Rejected

- Egress proxy (Squid/Envoy) as the only control (another component in the critical path;
  tenant quota; still needs the fetch layer to validate redirects it does not see decrypted).
- Requiring Cilium/Calico FQDN policy in the core chart (CRD; not tenant-installable).
- Trusting `allowed_hosts` from the manifest alone (contributor-controlled).

## Consequences

- ADR-008 SSRF mechanism amended; `docs/threat-model.md` rows "SSRF via manifest URL" and
  "malicious redirects" cite this ADR.
- Phase 1 manifest: `allowed_hosts` validated against the host registry; `allow_insecure`
  field; Phase 2 fetch implements layer 2; Phase 5 chart implements layer 1, local CNI, V-11.
- `00` §4.3 gains V-11.
- Devil's advocate: `ipBlock.except` lists are static; a cloud metadata service on a different
  address (Azure `169.254.169.254` is the same; some private clouds differ) needs a values
  override. Values expose the list; the default covers the common ranges.

## Amendment 1 (2026-09-23) — a response-body cap

Layer 2 checked where a request goes but not how much comes back: a 30 s timeout, then whatever
the source sent went into memory (threat model §2). `Fetcher` now streams every response and
enforces `max_body_bytes` (default **64 MiB**; the largest committed payload, a month of SOAP
settlement, is about 2 MB). A declared `Content-Length` above the cap is refused before a byte is
read. A body without one is counted after content decoding, so a compressed bomb is measured by
what it expands to, and it is aborted past the cap. The error is `EgressError("response_too_large")`,
which is never retried. Error bodies are read to 2 KiB, since they only appear in messages.
Peers are now checked on the open stream, before the body is read. `05` C-64; the live smoke
passed on the streaming client (2026-09-23).

## Amendment 2 (2026-09-23) — enforced from the pod's first packet, not eventually

**Finding.** V-11 CONFIRMED layer 1 on the reference cluster (Calico, a long-running probe
pod). The same egress test on the demo (k3s, embedded kube-router) failed. The chart's policies
were right and enforced in steady state, but **a new pod's first packets left unfiltered**: a
capture pod reached the metadata service and a process pod reached OTE, each on its first
request, while the next request about a second later was rejected. A fresh process pod got HTTP
200 from `169.254.169.254` at start and was refused 15 s later. kube-router programs a pod's
policy after the pod is running. Cilium on kind programs it before, which is why the kind test
passed. On Hetzner the metadata service returns the server's `user_data`, which holds the k3s
join token, and the API port is public.

**Decision.** Chart value `egress.policyGate` (off by default; on in the demo and local values).
When on, every platform-image pod (capture, process, recapture, backfill, gaps, hooks,
replicate, tier) runs `energyctl wait-egress-policy` as its first init container. The gate
starts its main container only after a canary that every role's policy denies (the metadata
address, port 80) has been refused twice in a row, and it fails the pod closed after
`timeoutSeconds` if the canary stays reachable. The gate has no credential in its environment.
kube-router applies one pod's rules together, so once the canary is refused, the pod's egress
rules are in force. `05` C-65.

**What remains.** The gate protects the platform's pods, the ones that handle source payloads.
It does not cover other pods on the node, such as k3s's own system pods, which have no
NetworkPolicy at all. Blocking pod traffic to `169.254.169.254` at node level (an iptables
rule, or the provider's metadata firewall where one exists) is the complete control. On the demo
it is a change to the nodes and is recorded as the author's decision (`docs/threat-model.md`
§6). The egress-test Jobs (`deployment/local/egress-test-job.yaml`) stay ungated on purpose:
they measure the CNI, not the chart.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-4 · CONFIRMED (NetworkPolicy creatable; enforcement not
tested → V-11); 2026-09-19 · V-9 · CONFIRMED (no proxy on the reference cluster); 2026-09-23 · V-11 · CONFIRMED (egress `NetworkPolicy` enforced by the
reference cluster's Calico for a tenant namespace, steady state).
