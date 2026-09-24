# Response to the Codex final review (2026-09-24)

| | |
|---|---|
| Reviewed snapshot | `1701ac7` (README target list; the deployed commit is `45b46ec`, one README change earlier) |
| Review material | `codex-review/2026-09-24/` (README, 01–06, `evidence/`) — committed verbatim as 8a466d8, not edited |
| Independent check | both probe scripts rerun on the maintainer's machine 2026-09-24 before this response: **DC-01 … DC-08 and AE-01, AE-03, AE-04 all reproduce**; the two editorial discrepancies confirmed by reading the lines |
| This document | one verdict per finding, the reasoning, and where the finding is closed |
| Plan | `docs/plans/review-2.md` (today's five tasks; Phase 10 for the rest) |

The review's overall verdict is accepted: the platform ingests real data, the contributor path
works for admitted sources, the deployment and recovery machinery is real, and the system does
**not** yet keep its output correct through every correction, overlap and recovery it promises.
Eight P1 findings are open. None is a fixture, a test or a documentation problem: they are
behaviours of the runtime that the existing 887 tests do not exercise. They are recorded, the
completion claim in the README is bounded accordingly, and they are planned as Phase 10 after
delivery. Nothing in the review is declined; the reviewer's readings of the contracts and the
rendered charts were checked and are correct.

## Verdicts — data correctness (`03-data-correctness.md`)

### DC-01 — a correction captured during a ledger outage is never reconciled (P1) — accepted

Reproduced: Bronze holds attempt 2 with `content_changed=true`, the run still points at attempt 1,
`reconciled=0`, current price unchanged. The cause is exactly as stated: `ensure_run` advances a
run only when it has no capture id, so orphan reconciliation (ADR-024) recovers *missing* runs
and never a *newer capture of an existing run*. ADR-024 promised "the durable boundary is the
Bronze entry"; the ledger has to follow every generation of that boundary, not only the first.
Phase 10 task 10.3: capture generations in the ledger, reconciled and queued across the
configured correction window, with the review's crash-matrix case (processed run, new correction,
then an unchanged poll) as the negative test on PostgreSQL.

### DC-02 — recapture does not fence an in-flight process claim (P1) — accepted

Reproduced: worker 1's commit for A succeeds after B was registered, the run ends `processed`
with B's capture id and A's rows. The fence protects against a *replacement claimer*
(ADR-024's lease fencing) and was never bound to the capture the claim read. Same task 10.3: a commit carries
the generation it processed and loses to a newer registration, or leaves the newer generation
pending. Tested as concurrent PostgreSQL transactions, not sequential recaptures.

### DC-03 — the canonical current view ignores T1/T2 ownership (P1) — accepted

Reproduced: SOAP `999.00` then XLSX `170.13` a minute later → canonical `170.13` from XLSX, and
`transport="soap"` on the current view returns nothing. `01` §3 reconciliation rule 2 says T1 is the system of
record for `price_vwap` and `volume_total`; the registry carries `owner_transport`; ADR-023 decision 3
ranks by ordering instant, contract semver and derivation, and never consults the owner. The
existing "ownership" test in `tests/store/test_store.py` uses equal values and equal instants and
proves nothing about the rule. The live database confirms the effect (288 current XLSX rows
against 96 SOAP rows for each owned metric). Phase 10 task 10.1 amends ADR-023 decision 3: a latest value
per transport stays selectable, the canonical row is the owner's when the owner has one, and
reconciliation compares transport-specific latest values.

### DC-04 — an A → B → A provider reversion leaves B current (P1) — accepted, design contradiction

Reproduced: the third capture is `content_changed=true`, processing is `noop/0`, current stays
B. This follows from ADR-023 decision 2 as written ("exact retry inserts nothing", keyed on payload
hash), which resolved review-1 F05 but cannot tell a retry of one capture from a *new occurrence*
of a payload seen before. The reviewer is right that the third capture is genuinely newer.
Phase 10 task 10.2 amends ADR-023 decision 2 with occurrence lineage: an exact retry of one capture is
still a no-op, a new capture of an old payload is an occurrence eligible for current selection.
Acceptance: A→B→A ends at A; replaying the *old* A after B stays at B.

### DC-05 — a claimed replay is abandoned when its worker dies (P2) — accepted

Reproduced: `lease_expired=true`, `pending_runs=0`, the replay attempt still owned by the dead
worker. `pending_runs` selects processed runs with a queued replay only while `lease_owner IS
NULL`; the initial-process lease test covers a run, not a replay. Phase 10 task 10.4.

### DC-06 — concurrent capture writers overwrite one capture-log entry (P1) — accepted

Reproduced with two threads and a barrier: two blobs, two hashes, one log entry, same capture
id. The attempt number is `len(existing) + 1` and the log write is an unconditional PUT on every
backend. `concurrencyPolicy: Forbid` prevents the scheduled overlap and nothing else (a manual
Job, a backfill and a correction of the same run can overlap). Phase 10 task 10.5: conditional
create (`If-None-Match: *` on S3, `O_EXCL` on files, a lock in memory) with retry on conflict,
tested against MinIO. ADR-024's "durable boundary" needs this to be true.

### DC-07 — a full rebuild restores deleted, known-wrong data and the drill passes (P1) — accepted, disclosed

Reproduced: `drill_ok=true`, `extra_versions=192`, the removed rows current again in the rebuilt
store. `docs/07` §4.3 and §5.3 say this ("the nine deleted versions come back as extra, by
design"). The reviewer's point stands above the disclosure: the drill proves that live versions
are preserved, not that live *decisions* are; a deletion recorded only in a runbook is not a
durable input to reconstruction. Phase 10 task 10.6, new ADR-038: an `invalidations` table
(capture id, derivation, reason, who, when) that replay, restore and the drill apply, with the
22 September decision recorded there by the author (Level 3), and "extra" classified against it.
Raw evidence stays immutable.

### DC-08 — freshness counts historical and other targets' rows (P2) — accepted

Reproduced both ways: a NULL correction leaves the period counted, and a monthly target with no
run reports `complete` from daily version-0 rows. `count_periods` groups by dataset and transport
over the whole table; ADR-037 said "current view" and `01` §3 reconciliation rule 4 says completeness is per
owning transport and metric set. The live snapshot's shared newest-delivery timestamps for the
monthly targets are that defect. Phase 10 task 10.7: freshness scoped to the target's owning
metrics, source version and requested delivery partition, monthly targets judged against their
month with the publication window from `06` §9.1. The reviewer's caution is adopted: seven
configured targets are not seven proven data streams; the monthly targets first run on
2026-10-01.

## Verdicts — deployment and HA (`04-deployment-and-ha.md`)

### DEP-01 — hourly replication does not meet the stated cross-provider RPO (P1) — accepted, disclosed

Correct reading of ADR-002's table (Bronze RPO ≤ the polling interval, Silver ≤ 15 min) against
the demo's `:17` hourly replica job: the bound holds for a database-node loss while store A is
up, not for a store-A or provider loss. ADR-036 does not state the RPO per failure domain.
Phase 10 task 10.8: state it (database-node loss, store-A loss, whole-cluster loss), either
shorten replication to the bound or amend the bound, and add a replica-age metric and alert.
The daily drill stays what it is: proof of recoverability of the replicated history.

### Topology — one k3s server, one PostgreSQL pinned to it — accepted, disclosed (ADR-028)

ADR-028 accepted a non-HA control plane for the demo on cost grounds and says so. The reviewer
counts it against the brief's HA requirement, and that is fair: the delivered profiles
demonstrate durable capture, independent copies and rebuild, not control-plane or database
failover. The README's completion statement now says exactly that (R2.5). A three-server
embedded-etcd profile with CNPG replication is the production path the own-cluster README
describes; it is not delivered, and the README no longer implies otherwise.

### DEP-02 — CNPG/external modes render but their recovery paths are not implemented (P1) — accepted, deferred

Correct: the CNPG render has no backup resources, the drill still expects the StatefulSet
layout and `POSTGRES_PASSWORD`, and the `imageName` has no version tag. ADR-036's decision describes a
contract the chart does not implement for these modes. Phase 10 task 10.9 first makes the render
*refuse* the combination (drill enabled with `cnpg`/`external`) rather than accept it silently;
the implementation follows when a CNPG cluster exists to test against. The demo runs the
StatefulSet mode and is unaffected.

### DEP-03 — the Cilium FQDN option leaves public 443 allowed (P2) — accepted, deferred

Correct by rule semantics: the standard NetworkPolicy's public-443 rule is unconditional, so the
optional CiliumNetworkPolicy adds nothing. The option is off in every delivered profile
(ADR-026: the hostname allowlist is enforced in `energy_platform.fetch`, the network layer is
coarse). Phase 10 task 10.9 makes the broad rule conditional on `fqdnPolicy=none`.

### DEP-04 — an empty external Postgres CIDR list opens 5432 to every destination (P2) — accepted, **fixed today**

Correct: an empty `to:` list is "all destinations" in the API, and the schema did not require a
destination. Fixed in R2.3 the way the object-store rule already is: the template `fail`s when
`postgres.mode=external` and `egress.postgres.cidrs` is empty; negative test
`tests/harness/test_chart.py::test_external_postgres_mode_refuses_an_empty_destination_list`;
row C-68 in `docs/05`.

### DEP-05 — the metadata canary cannot prove CNI readiness once the node blocks metadata (P2) — accepted, disclosed

Correct: after the node-level DROP (`docs/07` §2.1), a refused connect to the metadata address is
true whether or not the pod's policy is installed, so the gate's evidence is weaker than ADR-026
amendment 2 describes. The init-container delay is what actually covers the kube-router window on
the demo. Phase 10 task 10.9: a readiness signal that depends on the per-pod policy, and the
first-packet test rerun with the node block on. The runbook wording is corrected in the same task.

### Further checks the reviewer lists (data volume on later boots; backup-age alerts) — accepted as Phase 10 acceptance items

Both are added to task 10.8/10.9 acceptance: a restart without the data device must not start
k3s against an empty local path; `pg-backup` and `pg-wal-ship` failures and WAL age get alert
rules (today only restore and replication Job failures do).

## Verdicts — agent constraints (`02-agent-constraints.md`)

### AE-01 — triage reports `no_drift` after a renamed supported field (P2) — accepted

Reproduced: `@value1` → `@value1New` yields 96 NULLs, `unknown_field` events in the pipeline,
and `no_drift` from triage; a renamed OTE `<Date>` yields zero observations and `no_drift`. Two
causes, both as stated: the safe-name rule excludes the platform's own `@attr` convention, and
the inventory is built only from records the old parser still recognises. A false healthy
diagnosis is the one thing the triage path must not produce. Phase 10 task 10.10: inventory
decoded fields independently of mapping, admit `@attr`, carry the pipeline's drift events into the
report, and two negative tests (the ČEPS attribute rename, the OTE time-field rename).

### AE-02 — the guide's primary bundle route refuses the contributor's own dirty checkout (P2) — accepted

Correct by control flow: `apply_pr_bundle` refuses any non-empty `git status`, and the scaffold
has just created untracked files in that checkout. The acceptance runs used plain Git, so the
bundle block was never exercised as written. Phase 10 task 10.10 makes plain Git the primary route
in `docs/08` §9 and documents the bundle route as "apply into a clean second checkout with
`--repo`"; the exact command sequence gets run in a disposable repository.

### AE-03 — a failing target test can receive a green bundle (P2) — accepted, **fixed today**

Reproduced: `run_target_tests.ok=false`, `gate_report.ok=true`, bundle written with the failing
file inside and a body saying the gates were green. `gate_report` runs surface, admission and
goldens; the target's pytest is `run_target_tests`, a separate verb the sandbox deliberately
lacks. The reviewer's second option is taken: the bundle is an explicit partial-check artifact.
R2.4: `gate_report` records `tests: "not run by pr-bundle"`, the default body names the three
gates that were green and states that the target's pytest, lint and types are run by CI, the CLI
and MCP wording and `docs/08` §9 say the same, and a test asserts the body names the omitted
checks. Requiring pytest in the bundle would make the sandbox unable to open a PR at all
(ADR-007 mode 2); CI remains the boundary, as the reviewer notes.

### AE-04 — constrained MCP cannot produce the admission request it asks for (P2) — accepted

Reproduced: `admission_request` is not a tool, and `write_target_file` refuses the path. The
Route B instruction is right and the constrained agent cannot carry it out; the guide does not
say that it must hand over. Phase 10 task 10.10: a scoped `admission_request` tool that writes
only `docs/admissions/<id>.md` to the outbox (ADR-007 tool table amended, ADR-022 pointer), and a
Route B test run with the sandbox's tool surface only.

### Scope limits the reviewer states — accepted as stated

Custom `parser.py` is accepted by the surface and never executed (G13; the scaffold still offers
it — Phase 10 task 10.10 makes `validate` refuse a supplied parser until a loader exists); the
LLM backend is a stub (G12); the blind runs prove the declarative path for an admitted source
family, not an arbitrary new shape; sandbox verification is static. All four are in the README's
"Deliberately not built" table already; the completion statement now points at them.

## Verdicts — verification and editorial (`01`, `05`, `06`)

- **README says 672 rows await a decision** — accepted, fixed today (R2.3): the line now records
  the 6 048-version deletion of 2026-09-24 and the replay warning, consistent with `docs/07` §4.3.
- **"About 13 minutes"** — accepted, fixed today (R2.3): `docs/07` §5.3 now gives the two phases
  separately (777 s against the restored database; 1 216 s, about 20 minutes, for the Bronze-only
  rebuild; about 34 minutes for the whole two-phase Job) and says none of them is an
  infrastructure-loss RTO.
- **Live smoke is vacuous on zero recognised records** — accepted; folded into AE-01's task
  (the smoke asserts a non-zero record count on days the source has data).
- **"Seven targets" ≠ seven producing streams** — accepted; the README says which five have data
  and that the monthly targets first run on 2026-10-01.
- **Fresh clean-OS and cluster bring-up were not rerun** — noted; the recorded runs in `docs/07`
  §8 remain the evidence and are labelled as recorded, not fresh.
- **The reviewer's own qualification of the previous round** ("its obsolete 'no platform code'
  assessment does not describe this implementation") — noted with thanks; both rounds stay in
  the repository as they were written.

## Not changed, and why

- `docs/00`, `01`, `02` are untouched (frozen); DC-03/DC-04/DC-08/DEP-01 amend ADR-023, ADR-024,
  ADR-036 and ADR-037 in Phase 10, with dated pointers in `02` as before.
- No runtime behaviour of the correction, current-view, replay or drill paths was changed today:
  those fixes share one identity model and get one design pass first (Phase 10).
- The live database and the demo cluster were not touched; the 22 September invalidation row is
  an author action once ADR-038 exists.
- `codex-review/2026-09-24/` is verbatim.

## Closure — Phase 10, 2026-09-24 (`docs/plans/phase-10.md`)

Every finding was closed the same day, one commit each, with the review's counterexample as a
negative test (on PostgreSQL where the store is involved). The reviewer's probe scripts were
rerun afterwards, probe by probe:

| Finding | Closed by | Probe now |
|---|---|---|
| DC-01, DC-02 | bba45dd — ADR-024 amendment 1: a recapture bumps the fence, reconcile advances generations, window + correction days | assertion fails (defect gone) |
| DC-03 | 3bf5201 — ADR-023 amendment 1: owner first, per-transport current view, migration 0004 | assertion fails |
| DC-04 | a39193b — ADR-023 amendment 2: occurrences, migration 0005 | assertion fails |
| DC-05 | 7f39b06 — ADR-024 amendment 2: expired replay attempts reclaimed | no longer runs (`pending_runs` takes `now`); `tests/store/test_store.py::test_review2_dc05_…` |
| DC-06 | 971e724 — ADR-024 amendment 3: create-only entries, retry on the next attempt | no longer runs (its barrier expects one listing per writer; the loser now lists again); `tests/bronze/test_bronze.py::test_review2_dc06_…` |
| DC-07 | 07d4181 — ADR-038: durable invalidations, migration 0006, `energyctl invalidate` | **still asserts**: the probe models the retired repair (a bare Silver deletion with no recorded decision), which a rebuild can only undo; the supported repair is the invalidation, proved by `tests/runtime/test_review2.py::test_dc07_…` |
| DC-08 | 04af64d — ADR-037 amendment 1: target-scoped freshness, month partitions | no longer runs (`count_periods` takes the target scope); `test_review2_dc08_…` on both stores and through the verb |
| DEP-01 | 1c69fce — ADR-036 amendment 2: RPO per failure domain, 15-minute replication on the demo, staleness alerts | — |
| DEP-02, DEP-03, DEP-05 | 10c3d60 — ADR-036 amendment 3, ADR-026 amendment 3: modes refuse the drill, FQDN mode replaces the coarse rule, host canary | — |
| DEP-04, AE-03, editorial | 16605ae, 3482364, 9d57391 (before Phase 10) | — |
| AE-01, AE-02, AE-04, scope limit 1 | b8749d9 — mapping-independent inventory, plain-Git route, `admission_request`, parser refusal | AE-01 and AE-04 `reproduced: false`; AE-03 stays `true` by design (the bundle discloses the checks it does not run instead of running pytest, which the sandbox lacks) |
| Topology | not changed — the demo stays one server (ADR-028); the README says so | — |

Left for the author (Level 3): record the nine wrong 22 September captures with `energyctl
invalidate` (`docs/07` §4.3), rerun the three first-packet egress Jobs with the node block on
(`docs/07` §2.1), and the CNPG/external backup chains when a cluster with the operator exists.
