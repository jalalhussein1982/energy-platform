# Proposed remediation and acceptance

This is a proposal for agreement after the review. **No fix has been implemented.** Changes are platform work under the maintainer protocol; frozen contracts should change through ADRs where necessary.

## 1. Repair current-data and recovery invariants

DC-01–08 share capture/observation identity and should first receive one coordinated design review, followed by separate reviewable commits.

| Required behavior | Findings | Acceptance test |
|---|---|---|
| Recover durable corrections after lost ledger acknowledgment | DC-01 | Process A; capture B during DB outage; recover; ordinary reconcile/process must produce B, including a subsequent unchanged poll and corrections older than the default reconcile window. |
| An old worker cannot finish newer work | DC-02 | Hold A's claim; register B; commit A. A must lose its generation or leave B pending. Exercise concurrent PostgreSQL transactions. |
| Canonical values honor source ownership | DC-03 | Different SOAP/XLSX values, both arrival orders; canonical selects owner, reconciliation can query each transport's latest value. |
| Distinguish new occurrence from exact retry | DC-04 | A→B→A ends at A; replaying old A after B stays at B; exact retry introduces no duplicate occurrence. Preserve append-only lineage. |
| Reclaim expired repair work | DC-05 | Worker dies after replay claim; after lease expiry normal processing completes repair, with old worker fenced. |
| Every acknowledged raw capture retains discoverable provenance | DC-06 | Two overlapping writers with different responses retain distinct immutable entries or explicitly retry/refuse. Exercise isolated S3-compatible storage. |
| Preserve invalidation decisions through rebuild | DC-07 | Persist a known-bad capture/derivation decision; full rebuild excludes its output while retaining raw evidence. The September T2 repair survives reconstruction. |
| Freshness belongs to the target's delivery partition | DC-08 | Daily v0 cannot satisfy monthly v1/final v2; historic non-NULL cannot hide current withdrawal; missing owning metrics remain incomplete. |

Output-affecting fixes need an explicit new derivation. Identity uses `energy_platform.__version__` (currently `0.0.1`), contract, mapping and parser reference; a new image digest alone does not automatically change it. Verify same-Bronze/new-implementation replay actually appends and selects the correction.

Before any live repair, prepare an exact dry-run inventory of affected captures, derivations and canonical rows. Preserve raw evidence; unrecorded deletion is not a durable invalidation mechanism. Live mutation would need separate authorization: this review is read-only.

## 2. Agree and prove high availability

Define failure domains and bounds separately: worker failure, database process/node loss, control-plane loss, store-A/provider loss and full environment reconstruction.

- **DEP-01:** replicate and monitor fast enough for the agreed independent-copy RPO, or amend the objective. Measure newest recoverable capture/WAL age in B, not just job success.
- Provide reproducible automatic database and scheduler/control-plane recovery, or explicitly limit the delivered profile to a non-HA demo. More agent nodes alone do not provide it.
- **DEP-02:** implement actual CNPG backup/restore and valid image/version configuration; give external mode a usable scratch-restore contract. Reject unsupported combinations until they work.
- After data fixes, run isolated failover and B-only recovery. Include configuration/identity restoration and resumed fresh output in RTO, not only replay duration on warm infrastructure.
- Establish a real scraper and alert receiver. Demonstrate notifications for missing/stale WAL shipment, a dead gap detector, late data and failed correction/restore; distinguish source outages from pipeline failures.

## 3. Close deployment boundary gaps

- **DEP-03:** remove additive broad public HTTPS permission when FQDN restrictions are selected; test declared and unrelated hosts on the chosen CNI.
- **DEP-04:** empty external database destinations must fail rendering.
- **DEP-05:** use meaningful per-pod policy readiness; an independently blocked metadata address cannot prove it. Repeat first-packet tests with node hardening enabled.
- Put proven hardening/reconstruction steps into the declarative path or clearly enumerate and verify the remaining operator dependencies.

## 4. Make the contributor guide executable

- **AE-01:** inventory fields independently of successful parsing; test real XML attributes and required-field renames. Distinguish genuine empty data from unrecognized nonempty data.
- **AE-02:** choose a publish workflow that works from the contributor's actual dirty/untracked checkout, and test the exact guide commands.
- **AE-03:** require target tests or state explicitly which bundle checks were omitted; avoid an unqualified green verdict.
- **AE-04:** provide a scoped MCP admission artifact or an explicit structured handoff.
- Keep custom parsers and the real LLM backend visibly deferred; reject ignored custom code clearly. An unfamiliar-source trial is needed for a broader extension claim.

## 5. Repeat acceptance and update the completion statement

Run ordinary gates plus new counterexamples on the agreed commit. Repeat independent fixture arithmetic after mapping changes. Perform a separately authorized deployment/failure exercise; local tests do not establish live acceptance.

Publish commit/image, command, environment, result, observed freshness, recoverable-data age, recovery duration and exceptions. Correct README's stale T2 incident and distinguish the 777-second restored-database phase, 1,216-second Bronze rebuild, whole job and infrastructure RTO. Report seven configured targets separately from streams observed producing scheduled data.

**Suggested decision:** retain the architecture and substantial implementation; agree a focused correctness/recovery phase first. Reassess full HA completion after those invariants and the chosen deployment profile are demonstrated.
