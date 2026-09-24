# Plan — Review 2: Codex final review against the original assignment (2026-09-24)

| | |
|---|---|
| Goal | Answer every finding of `codex-review/2026-09-24/` with a verdict, fix today what is small and safe, bound the README's completion claim honestly, and lay out the correctness phase (Phase 10) that closes the P1 data findings after delivery. |
| Inputs | `codex-review/2026-09-24/` (README, 01–06, `evidence/`), the two probe scripts (rerun on this machine 2026-09-24: all 11 counterexamples reproduce), ADR-002, ADR-023, ADR-024, ADR-026, ADR-028, ADR-033, ADR-036, ADR-037, `docs/07` §4.3 and §5.3. |
| Do not | Start the correctness phase on delivery day. Edit `docs/00`, `01`, `02` (frozen; amend by ADR). Weaken a gate to make a probe pass. Touch the live database or the cluster. Rewrite the review. |
| Verdict rule | A finding is *accepted* when its probe reproduces here or its render/contract reading checks out; *accepted, disclosed* when the behaviour is a recorded design limit the brief still counts; *deferred* when it lives in a mode the demo does not run. Nothing is declined outright. |

## Triage summary (full text in `docs/reviews/2026-09-24-codex-review-response.md`)

| Finding | Verdict | Where it is closed |
|---|---|---|
| DC-01 correction lost after a ledger outage | accepted, P1 | Phase 10 task 10.3 (ADR-024 amendment: capture generations) |
| DC-02 recapture does not fence an in-flight claim | accepted, P1 | Phase 10 task 10.3 |
| DC-03 current view ignores T1/T2 ownership | accepted, P1 | Phase 10 task 10.1 (ADR-023 amendment: owner-aware current view) |
| DC-04 A→B→A reversion leaves B current | accepted, P1, design | Phase 10 task 10.2 (ADR-023 amendment: occurrence lineage) |
| DC-05 claimed replay abandoned after a crash | accepted, P2 | Phase 10 task 10.4 |
| DC-06 concurrent capture writers share a log entry | accepted, P1 | Phase 10 task 10.5 (ADR-024 amendment: conditional create) |
| DC-07 rebuild restores deleted wrong data | accepted, P1, disclosed | Phase 10 task 10.6 (ADR-038: durable invalidation decisions) |
| DC-08 freshness counts other targets' rows | accepted, P2 | Phase 10 task 10.7 (ADR-037 amendment) |
| DEP-01 hourly replication vs the 15-minute RPO | accepted, disclosed | Phase 10 task 10.8 (ADR-036 amendment: state RPO per failure domain; shorter replication or an amended target) |
| DEP-02 CNPG/external drill paths unimplemented | accepted, deferred | Phase 10 task 10.9 (refuse at render until implemented) |
| DEP-03 Cilium FQDN option leaves 443 open | accepted, deferred | Phase 10 task 10.9 |
| DEP-04 empty external Postgres CIDR list fails open | accepted, **fixed today** | R2.3 |
| DEP-05 metadata canary cannot prove CNI readiness | accepted, disclosed | Phase 10 task 10.9 |
| AE-01 triage says `no_drift` on a renamed field | accepted, P2 | Phase 10 task 10.10 |
| AE-02 bundle workflow needs a clean second checkout | accepted | Phase 10 task 10.10 (docs/08 primary route becomes plain Git) |
| AE-03 green bundle without target tests | accepted, **fixed today** | R2.4 (the bundle names what it did not run) |
| AE-04 constrained MCP cannot file an admission request | accepted | Phase 10 task 10.10 |
| Single-server demo topology | accepted, disclosed (ADR-028) | README completion statement (R2.5); a production profile is out of the delivered scope |
| README says 672 rows; docs/07 "about 13 minutes" | accepted, **fixed today** | R2.3 |

## Ordered tasks (today)

| # | Task | Acceptance check | Commit |
|---|---|---|---|
| R2.1 | `codex-review/2026-09-24/` committed verbatim | folder tracked, `make check` and `secret-scan` green | `docs(review): Codex review 2 … kept verbatim` — **done 8a466d8** |
| R2.2 | This plan and `docs/reviews/2026-09-24-codex-review-response.md`: one verdict per finding, the reasoning, where it is closed | every finding of the review's six files has a verdict | `docs(review): response to Codex review 2` |
| R2.3 | Editorial and fail-open fixes: README incident line (6 048 versions deleted, not 672 pending); `docs/07` §5.3 states the two phases and the whole job separately (777 s, 1 216 s ≈ 20 min, ≈ 34 min end to end) and does not call any of them an infrastructure RTO; `networkpolicy.yaml` refuses `postgres.mode=external` with no `egress.postgres.cidrs` (`fail`, as the object-store rule does), negative test in `tests/harness/test_chart.py`, row C-68 in `docs/05` | render with external mode and no CIDR exits non-zero; existing renders unchanged | `fix(chart): external Postgres mode refuses an empty destination list …` and `docs: README incident line and the RTO figures …` |
| R2.4 | AE-03: `gate_report` records `tests: not run by pr-bundle`; the default bundle body says which gates were green and that the target's pytest, lint and types are CI's; CLI and MCP `open_pr` wording, `docs/08` §9 comment, C-51 wording; test asserts the body names the omitted checks | `tests/harness/test_pr_bundle.py` green with the new assertion | `fix(harness): the PR bundle says which gates it ran …` |
| R2.5 | README completion statement bounded: "complete as delivered; review 2 lists 8 P1 correctness findings, open, planned as Phase 10" with the link; `docs/README.md` index row for both reviews; roadmap phase map row 10 and Phase 10 stub pointing here; `docs/progress.md` entry; memory | `make check` green | `docs: bounded completion statement, Phase 10 stub, progress` |

## Phase 10 — correctness and recovery (after delivery; not started)

One coordinated design pass first (the DC findings share capture and observation identity), then one commit per task, each with the review's acceptance test as its negative test on PostgreSQL (`make db-test`), not only the memory store.

| # | Task | Amends | Acceptance (from `codex-review/2026-09-24/06`) |
|---|---|---|---|
| 10.1 | Owner-aware current view: latest value per transport is selectable; the canonical row per observation identity is the owning transport's when it has one; reconciliation compares transport-specific latest values | ADR-023 decision 3 | different SOAP/XLSX values, both arrival orders: canonical = SOAP; `transport="soap"` filter never empty when SOAP rows exist |
| 10.2 | Occurrence lineage: an exact retry of one capture inserts nothing, a new capture of a previously seen payload records an occurrence and is eligible for current selection | ADR-023 decision 2 | A→B→A ends at A; replaying old A after B stays at B; no duplicate on retry |
| 10.3 | Capture generations: the ledger records which capture generation a run has processed; reconcile queues any newer durable generation, including after a lost acknowledgment and beyond the 48 h window when asked; a process commit carries its generation and loses to a newer registration | ADR-024 | DC-01 and DC-02 scripts on PostgreSQL; a subsequent unchanged poll does not hide the correction |
| 10.4 | Replay reclaim: an unfinished replay attempt with an expired lease is pending work again; the dead attempt's outcome is recorded | ADR-024 | DC-05 script: after lease expiry, normal processing completes the repair |
| 10.5 | Collision-safe capture log: conditional create (`If-None-Match: *` on S3, `O_EXCL` on files, a lock on memory) with retry on conflict; attempt ids never reused | ADR-024 | two overlapping writers keep two entries or one refuses; tested against MinIO in `make db-test`'s sibling target |
| 10.6 | Durable invalidation: an `invalidations` table (capture id, derivation, reason, who, when) applied by replay, restore and the drill; the 22 September decision recorded there; the drill's "extra" classification checks it | new ADR-038 | DC-07 script: rebuild excludes the invalidated output and still reports OK; raw evidence untouched |
| 10.7 | Target-scoped freshness: counts over current rows of the target's owning metrics, source version and requested delivery partition; monthly targets judged against their month, with a publication deadline from `06` §9.1 | ADR-037 | DC-08 scripts: v0 rows cannot complete a v1 target; a NULL correction withdraws a period |
| 10.8 | RPO per failure domain stated in ADR-036 (database-node loss, store-A loss, whole-cluster loss); replication interval matched to the store-A bound or the bound amended; a replica-age metric and alert | ADR-036, `02` pointer | an isolated drill with A unavailable measures newest recoverable capture and WAL from B |
| 10.9 | Deployment modes: render refuses `cnpg`/`external` with the restore drill enabled until their backup chain exists; Cilium FQDN mode drops the broad 443 rule; the policy gate distinguishes "metadata blocked at the node" from "policy installed" | ADR-026, ADR-036 | renders per mode assert the rule set; first-packet test rerun after the node block |
| 10.10 | Contributor path: triage inventories decoded fields independently of mapping and admits `@attr` names; `docs/08` §9 primary route is plain Git (bundle route says `--repo <clean checkout>`); MCP gains a scoped `admission_request` that writes only `docs/admissions/<id>.md` to the outbox | ADR-007 tool table, ADR-022 | AE-01 renames detected; the guide's commands run in a disposable repository; Route B completes with the sandbox's tool surface |

## Verification before each commit

`make check`; `make db-test` for 10.1–10.7; `make helm-lint` for R2.3 and 10.9.

## Stop conditions

- A task needs a live mutation (the 22 September invalidation row, a new replication schedule on the demo) → hand the command to the author, as in Phase 9.
- A task needs a new dependency → ADR + allowlist first.
