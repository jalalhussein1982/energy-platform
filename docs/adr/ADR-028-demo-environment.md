# ADR-028 — Demo environment: Hetzner cluster, OCI second store; MetaCentrum stays reference-only

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | amends ADR-001 (amendment) rule 4 and rule 5; refines D-1 and D-3 (`02-architecture-decisions.md` §4.2) for the environment the author operates |
| Supersedes | — |

## Context

ADR-001 (amendment) makes MetaCentrum / e-INFRA CZ the **reference environment**: the assumption base, verified by one-off commands (V-4 … V-10), never named as production. Rule 5 and `03` Phase 5 then go one step further and make the reference cluster "the first real environment", i.e. a place where the platform runs continuously.

That step is not available. e-INFRA CZ access is granted for research and education to members of Czech academic institutions. This repository is a commercial evaluation deliverable for a company that holds no e-INFRA subscription. A scheduled ingestion workload serving that purpose is outside the acceptable use; a handful of read-mostly probes to learn the constraints of a shared Rancher tenant is not, and those probes are already recorded in `00` §5.

The deliverable still needs a **live instance** next to the blueprint: the evaluator should be able to open a running system, watch captures land, and see a restore drill pass, without building anything. The author holds two paid accounts for this: a Hetzner Cloud project and an Oracle Cloud Infrastructure (OCI) tenancy upgraded to pay-as-you-go. Neither is a Czech data centre (A-9), and neither is ČEZ's platform.

Facts that shape the choice, as of 2026-09-19:
- OCI halved its Always Free Ampere allowance on 2026-06-15 (2 OCPU / 12 GB); free ARM capacity in EU regions is frequently unavailable; ARM would force multi-arch image builds. OCI Object Storage keeps 20 GB free and exposes an S3-compatible API; retention is a bucket **retention rule**, not the S3 Object Lock API.
- Hetzner Cloud offers x86 VMs from about €4/month, an S3-compatible Object Storage (Falkenstein, Nuremberg), a maintained Terraform provider (`hcloud`) and predictable capacity. Object Lock support on Hetzner Object Storage is **unverified**.
- A-3 requires a second, *independently operated* object-store endpoint for the Bronze copy (ADR-002, ADR-021 §4). Two buckets at one provider satisfy the letter, not the intent.
- CLAUDE.md Authority: `terraform apply` and archive deletion are Level 3, forbidden to the agent.

## Decision

1. **Three environment words, fixed meanings.**
   - *Reference environment* = MetaCentrum / e-INFRA CZ. Assumption base only. **No scheduled workload, no Helm release, no bucket of ours is left running there.** One-off verification commands remain allowed and are recorded in `00` §5. ADR-001 (amendment) rule 5 is amended accordingly.
   - *Demo environment* = the environment the author operates and pays for, handed to the evaluator as a live instance. Defined by this ADR.
   - *Production* = ČEZ's platform (scenario A, B or C). Never the reference, never the demo.
   Environments are Helm values files and Terraform roots. **There is no `demo` profile**; the profile set of ADR-001 (amendment) is unchanged.

2. **Demo cluster on Hetzner Cloud, built by the `own-cluster` profile, deployed with `tenant` values.**
   - `deployment/own-cluster/terraform/` gains a second root next to the OpenStack one. Both roots consume the same modules (`network/`, `nodes/`, `storage/`, `security/`) and the same cloud-init that installs k3s (D-1 shape unchanged; k3s ships an embedded NetworkPolicy controller, so ADR-026 layer 1 is enforced without a CNI swap). The `openstack` root stays mock-tested in CI (`terraform test`); the `hcloud` root is the one that is applied.
   - Sizing: two `cx22` nodes (2 vCPU / 4 GB each), one private network, one firewall allowing 443 in and 6443 from the author's address only, one volume for Postgres.
   - The platform is installed into a namespace with a **namespace-scoped `Role` and no cluster rights**, using `deployment/tenant/values-demo.yaml`. The demo therefore proves both the `own-cluster` Terraform path and the `tenant` chart contract (no CRDs, `restricted` PSS) on the same cluster. Anything in the chart that only works with cluster rights is a defect, not a demo feature.
   - Deploy identity follows the federation clause of ADR-015: k3s runs with a structured `authentication-config` that trusts GitHub Actions' OIDC issuer; the deploy job exchanges its job token for the namespace-scoped identity. No long-lived kubeconfig or Rancher-style token exists in CI. If V-14 refutes this on k3s, the fallback is the ADR-015 two-token shape with a namespace-scoped ServiceAccount token, expiry recorded, and this ADR is amended.

3. **Bronze store A on Hetzner Object Storage; Bronze store B on OCI Object Storage (Frankfurt).**
   - Store A is the hot bucket the capture jobs write to (`bronze.endpoint`). Versioning on; Object Lock on if V-12 confirms it, otherwise the same compensating control ADR-021 uses for a cold side without lock (copy-verify under the ledger, never overwrite by key) plus a bucket policy that denies `DeleteObject` to the capture identity.
   - Store B is the independent copy of ADR-002/ADR-021 §4: different provider, country, billing account and failure domain. It is written **only** by the replication job (`rclone`, ADR-021), through OCI's S3-compatible endpoint, with a bucket retention rule managed by Terraform (`oci` provider) standing in for Object Lock. The restore drill reads from B at least once per run (ADR-024 §2).
   - `bronze.tiering.mode = none` on the demo: at demo volumes a cold tier costs more in complexity than it saves, and the tiering probe (ADR-021 §3, ADR-025) still runs against store A so the deploy-time contract is exercised.
   - D-3 row for the demo environment reads: "A = Hetzner Object Storage (S3); B = OCI Object Storage (S3-compat) in another provider and country".

4. **Residency is declared honestly.** The demo asserts `residency: DE` for the cluster and store A, and `residency: DE` for store B (OCI Frankfurt). A-9 is unchanged for production (`residency: CZ`); the demo is a documented deviation, shown to the evaluator as an example of the attribute doing its job, not hidden.

5. **Cost and lifecycle guard.** Before the first `terraform apply`, both accounts carry a budget alert (Hetzner: €25/month; OCI: €10/month) and the ceilings are written into `deployment/own-cluster/README.md`. `terraform apply`, `terraform destroy` and any bucket deletion are run by the author (Level 3). The agent prepares plans (`terraform plan -out`) and reads state; it never applies.

6. **New verification rows in `00` §4, filled with real command output in `00` §5 before Phase 5 builds on them:**
   - **V-12** Hetzner Object Storage: versioning, Object Lock (`put-object-lock-configuration`, then `delete-object` on a locked version must fail), storage-class probe as in V-6, lifecycle acceptance, egress cost.
   - **V-13** OCI Object Storage via the S3-compatible endpoint: versioning, retention rule enforced (delete inside the retention window must fail), `rclone sync` A → B round-trip with checksum verification, cross-provider bandwidth for a full-Bronze mirror at demo volume.
   - **V-14** k3s structured authentication with the GitHub Actions OIDC issuer: a job token maps to the namespace-scoped identity; `kubectl auth can-i` shows namespace rights only; cluster-scoped verbs are Forbidden.
   - V-11 (tenant CNI enforcement on the reference cluster) remains a one-off probe and is still worth running; it informs the `tenant` profile's claims for scenario A, not the demo.

## Rationale

Using a provider the author pays for removes the terms-of-use problem and makes the live instance something the evaluator can reproduce on any IaaS with a Terraform provider, which is the sovereignty argument of ADR-001 stated in practice. Hetzner over OCI compute because x86 avoids multi-arch builds, capacity is predictable, and the price is within a few euros of free. OCI for store B because a second provider is what "independently operated" means, and its object storage stays inside the free allowance at demo volumes. Building the cluster with the `own-cluster` Terraform but deploying with `tenant` values costs nothing extra and turns the demo into a test of both profiles.

If the assumption "the evaluator wants a live instance" is false, the cost is a small monthly bill and one extra Terraform root that CI validates anyway. If Hetzner Object Storage turns out not to support Object Lock (V-12), the design degrades to the ADR-021 compensating control, which the reference environment already forced us to design.

## Rejected

- **Keep running on MetaCentrum** (roadmap Phase 5 as written): outside e-INFRA CZ acceptable use for a commercial deliverable; also not reproducible by the evaluator.
- **OCI only** (free ARM compute + OCI storage): halved free tier, unreliable ARM capacity, multi-arch images, and both Bronze copies under one account.
- **Hetzner only** (two buckets, two locations): same operator, same billing account, same control plane; fails the intent of A-3.
- **OCI Kubernetes Engine (OKE)** or any managed Kubernetes: replaces the D-1 answer (VMs + cloud-init k3s) with a vendor control plane, proves less of the Terraform path, and the evaluator's scenario B is an IaaS, not a managed cluster.
- **A fourth `demo` profile**: environments are values files and Terraform roots (ADR-001 amendment rule 1); a profile per environment is the "three charts, three drifts" mistake in a different coat.
- **Let the agent apply Terraform for the demo**: Level 3 in CLAUDE.md; unchanged.

## Consequences

- `02` ADR-001 "Reference environment" paragraph gains the demo-environment definition and the "no scheduled workload on the reference environment" sentence; "This is the first real environment (03 Phase 5)" under `tenant` now points at the demo cluster. `02` §4.2 D-1 gains the `hcloud` root; D-3 gains the demo row. (Reconciliation edits, not task edits; `00` §6 checklist.)
- `00` §2.1 `own-cluster` row: "Terraform on an IaaS — roots: `openstack` (reference, mock-tested), `hcloud` (demo, applied)". `00` §4 gains V-12, V-13, V-14. A-9 gains the note in §4 of this ADR.
- `03` Phase 5: deliverables reworded (tenant values deploy to the demo cluster; `hcloud` Terraform root; replication A → B across providers; cost guard; V-12 … V-14). Phase 8: the README's reproduce block gains "or open the live demo" with the credential hand-over path.
- ADR-001 (amendment) rule 5 amended by reference: "`tenant` values are first deployed for real on the demo cluster (ADR-028); the reference environment hosts no release."
- ADR-015 federation clause is now exercised for real (V-14) instead of being the hypothetical branch.
- Credentials for both accounts live outside the repository, like the reference-environment credentials; the CI secret set gains only what V-14 requires.
- Devil's advocate: the demo cluster is a two-node k3s with no control-plane HA, so a node loss is a demo outage. That is accepted: ADR-004's invariants are about **data** (Bronze in two failure domains, ledger-rebuildable Silver), not about cluster uptime, and the restore drill is what the demo exists to show. A second control-plane node is a values change, not a design change.

## Verification refs

`00-assumptions.md` §5: 2026-09-19 · V-6 · CONFIRMED (store A/B pattern and Object-Lock probe reused as the V-12/V-13 template); 2026-09-19 · V-8 · CONFIRMED (federation branch of ADR-015 now taken). V-12, V-13, V-14: **pending**, to be run by the author before Phase 5 Terraform work starts.

## Amendment 1 (2026-09-25) — the availability boundary of the demo, stated

**Finding (review 3 R1, `codex-review/01-deep-review.md`).** The consequences above accepted
that "a node loss is a demo outage" and left it there; the final report then described the
delivery as fulfilling the brief's high-availability requirement in full, with "the data
survives and the pipeline recovers" as the definition. Two readings of one topology. The
reviewer asks for either a demonstrated failover or an explicit boundary. This amendment is the
boundary; the demonstration is the author's decision.

**Decision.**

1. The demo is a **recoverable single-primary** deployment: one k3s server that is also the
   only PostgreSQL host (`values-demo.yaml` pins the StatefulSet to it), one agent, one
   PostgreSQL instance. What it delivers: durable capture in two failure domains (store A with
   Object Lock, store B at another provider), WAL and base backups shipped and replicated,
   physical restore and the Bronze-only rebuild drilled (ADR-036 §5, amendment 5), fenced
   workers, reconcile/backfill/replay/invalidation with no manual step. What it does **not**
   deliver: automatic failover of the database or of the control plane. The loss of the server
   is an outage that ends when an operator runs the restore procedure of `docs/07` §5 on
   replacement infrastructure; only its warm phases are measured (777 s and 1 216 s on
   2026-09-24), the whole-environment recovery is not (ADR-036 amendment 2 §4).
2. A-6's "recovery has **no manual step**" is true of the data path — a missed tick, a
   correction captured during a ledger outage, a wrong release, a known-wrong capture — and
   not of node loss on the demo. The assumption register is frozen; this amendment is where
   the qualification lives.
3. The production path is the own-cluster README's: three k3s servers with embedded etcd and
   CNPG with replicas (`postgres.mode=cnpg`), a values and Terraform change. It is **not
   exercised**: no node-loss drill, no failover measurement, and the CNPG backup chain refuses
   the restore drill until it exists (ADR-036 amendment 3). The README and the final report
   say "recoverable, not highly available in the failover sense" until one of the two is
   done; a green deploy and a ticked roadmap do not change that sentence.
4. Whether to fund and run a failover demonstration on the demo (a third server and a second
   PostgreSQL, roughly doubling the monthly cost of §5) is the author's decision and the one
   open acceptance item of review 3.

**Proof:** none — a boundary statement. `docs/07` §5 and the README's status line carry it.
