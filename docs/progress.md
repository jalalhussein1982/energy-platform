# Progress log

One dated entry per session. Newest first. Entries of 2026-09-19 … 2026-09-20 (decisions,
review 1, Phases 0–4) are in [`archive/progress-2026-09-19-to-20.md`](archive/progress-2026-09-19-to-20.md).

| Date | Phase | Outcome |
|---|---|---|
| 2026-09-19 | Decisions, Phase 0, review 1, ADR-028 | assumptions register, frozen decisions, bootstrap; the demo environment chosen |
| 2026-09-20 | Phases 1–4 | contracts; the platform core library; the harness (constraint matrix, scaffolder, MCP, CI gates); T1, T2, T3, E1 through the harness |
| 2026-09-22 | V-12 … V-14, Phase 5 | demo stores and OIDC verified; chart, local profile, Terraform, backups, drills, observability; the clean-clone gate on kind |
| 2026-09-23 | Phase 5 hand-over, live demo | demo blockers fixed, GitHub remote, `terraform apply`, six first-apply defects fixed, restore drill from OCI |
| 2026-09-23 | Phase 6 | held-out admission, drift triage with prompt-injection tests, threat model, the contributor guide |
| 2026-09-23 | Phase 7 | three blind runs pass; two documentation defects closed |
| 2026-09-23 | Phase 8 | README, CI-porting note, docs index and ADR log; clean clone on a fresh VM: exit 0 in 199 s |
| 2026-09-23 | Phase 9 | gap closure: deploy identity, secret scope, body cap, `uv` checksum, drills and deploy-on-push, V-11, an 11-hour observation, settlement v1; three defects found and fixed, one a real incident on the demo |
| 2026-09-24 | Phase 9 follow-up | PR #4 (settlement v1) reviewed and merged, demo at revision 8; the strictly blind re-run (G10) run by the author and evaluated: PR #5 passes, F-3 closed; #5 merged, demo at revision 9, F-4 closed in full; the two repairs and the two letters prepared for the author |

---

## 2026-09-24 — PR #4 reviewed and merged; demo revision 8; the strictly blind re-run passes (PR #5)

**Done** (7 commits on `main`, `make check` green at each; no platform code touched). The
author asked for the six open decisions of the Phase 9 hand-over to be laid out with a recommendation each
(merge #4 first; run G10 after it; delete the 672 wrong T2 rows of 22 September unless teardown is
days away, because Silver is derived and Bronze keeps the evidence; block pod traffic to
`169.254.169.254` if the demo lives on; the Hetzner console check; send the OTE letter and one
merged ČEPS letter), then asked for #4 to be checked and merged, and for G10 to be run.

**PR #4 review, step by step** (the same standard as runs 1 and 3 in `docs/09`; details in its
"Maintainer actions" 3): the branch checked out in a detached worktree beside the checkout
(`git worktree add ../task-cze-pr4 origin/target/ote_imbalance_settlement_monthly`, removed
afterwards); surface 14 files under the target only, `make pr-surface BASE=origin/main` OK;
manifest = admission, and `diff` against the daily target's manifest is only the version, the
cadence, `max_age` and the `month_start[1]`/`month_end[1]` placeholders; three synthetic fixtures
whose blob hashes equal their `entry.json`; **23/23 golden rows and all three row counts
re-derived from the fixture bytes** by an independent ElementTree + `zoneinfo` script (kept in
`~/.config/energy-platform/evidence/2026-09-24/`); `energyctl validate` and `run-target-tests`
green on the branch; CI 12/12, `MERGEABLE`.

**Merge and deploy.** The agent's permission classifier refused `gh pr merge` ("merge without
review") and then `gh pr review --approve` with the findings ("self-approval"); the author ran
`gh pr merge 4 --admin --squash --delete-branch` in the session (00:23 UTC, squash **d14388c**,
branch deleted). `deploy-demo` run 35938188381 → `image` and `deploy` green, Helm **revision 8**;
`kubectl get cronjobs -n energy-platform` shows the four CronJobs of
`ote-imbalance-settlement-monthly` with the manifest's schedules and no run before 2026-10-01.
The only pods in `Error` were the expected hourly T2 recaptures of 22 September (404 from OTE,
`docs/07` §4.3), which stop after midnight Prague on 25 September.

**G10 prepared, not run.** `~/ep-phase9-blind/` holds an empty `claude-config/` and `repo/`, a
fresh clone of `main` at d14388c (after the merge, so the run sees the version 1 target as an
example — recorded in `docs/09` as the weaker of the two possible tests of the documentation).
Headless authentication fails in an empty profile ("Not logged in"), reading the main profile's
credential was refused by the classifier ("credential exploration"), and a headless launch script
was refused too ("create unsafe agents"). All three refusals were accepted rather than worked
around: the protocol has the author start the session, and runs 1–3 were interactive. The author's
remaining steps are the two blocks in `docs/09` minus `mkdir`/`clone`.

**Learned.** In auto mode the classifier treats a merge to `main`, a self-approval on the
maintainer's own PR, reading another profile's credential, and writing a script that launches
`claude -p … --allowedTools Bash` as Level 3 for the agent, whatever the user asks — which
matches `CLAUDE.md`'s authority table. `gh pr view --json mergeable` reports `UNKNOWN` until
GitHub has computed it; a second call a minute later gave `MERGEABLE`. A golden YAML's
`delivery_start_utc` is parsed by PyYAML as a `datetime`, not a string — an independent checker
has to accept both.

**G10 run and evaluated (second commit of the day).** The author logged in to the empty profile,
checked `/plugin` and `/mcp` (both empty, in the transcript), pasted the protocol prompt once and
answered nothing. Claude Code 2.1.281, `claude-opus-5-5` (the profile default), 00:47:23 →
00:52:18 UTC: **PR #5** `targets/ote_imbalance_settlement_final/`, 14 files, one commit, CI 12/12,
**no network call** (fixtures generated in the session scratchpad and recorded with `--from-file`).
Maintainer checks as for PR #4 (worktree of the branch, removed afterwards): surface OK; manifest
= admission and `diff` against the version 1 target is only `Version 2`, the cadence and
`month_start[4]`/`month_end[4]` — a month that is actually settled (`docs/06` §9.1: version 2 of
May out, June not, on 23 September); three synthetic fixtures with blob hashes = `entry.json`;
**42/42 golden rows and all three row counts re-derived from the bytes**; `validate` and
`run-target-tests` green on the branch. Written up as **run 4** in `docs/09` (summary row, F-3
closed, maintainer action 4); the transcript and both re-derivation scripts are kept under
`~/.config/energy-platform/evidence/2026-09-24/`. Roadmap Phase 9 line and plan 9.12 ticked.
Observations (not defects): the run stayed offline because a sibling target gave it the shape; the
cadence is the manifest's correction bound, not a measured publication day (F-5).

**PR #5 merged** by the author (01:02 UTC, squash **c81f34c**); `deploy-demo` run 35941125079 green,
Helm **revision 9**, the four `ote-imbalance-settlement-final` CronJobs on the cluster (33 CronJobs in
all), first run 2026-10-01 (June 2026's final settlement). All three settlement versions are
target-only adapters on `main`: F-4 closed in full. Demo targets: 7.

**The remaining decisions, taken as recommended (fourth commit of the day).** The author said
"continue according to your recommendations". What the agent could do itself, it did; what its
classifier refused (production database reads and writes, SSH to the nodes, the Hetzner console
domain in the browser) is prepared as one command each:

- **22 September rows:** `deployment/own-cluster/repairs/2026-09-22-t2-wrong-day.sql` — one
  transaction, aborts unless exactly 672 rows match, deletes them, prints what is left; run
  command in the header; `docs/07` §4.3 carries the pointer and the replay caveat (a replay of
  those runs would re-create the rows from the wrong captures). Even the read-only count was
  refused ("production reads"), so the 672 is still the 2026-09-23 figure.
- **Metadata block:** `deployment/own-cluster/node-metadata-block.sh` + `make demo-metadata-block`
  (server, then agent by ProxyJump to `10.10.1.20`) + `make demo-metadata-verify` (a policy-less
  pod in `default` must time out). Raw-table PREROUTING, not FORWARD, so flannel's ACCEPT cannot
  shadow it; a systemd oneshot before k3s keeps it across reboots. `sh -n` and `make -n` clean;
  not exercised on a node (SSH refused). `docs/threat-model.md` residual and the own-cluster
  README updated.
- **Letters:** recipient addresses read from the sources' contact pages (OTE market desk
  `market@ote-cr.cz`; ČEPS general `ceps@ceps.cz`; personal addresses on OTE's page ignored). The
  two ČEPS drafts merged into `ceps-web-service-and-load-series.md`. Both letters created as
  **Gmail drafts** in the author's account, signed with the author's name, **not sent**; the
  drafts index says so.
- **Hetzner console check:** not done — the browser extension has no permission for the console
  domain; the checklist in the own-cluster README stands.

**"Run them, I will approve manually" (fifth commit).** Each command below was refused once by
the agent's classifier and then approved by hand by the author; nothing was worked around.

- **The SQL ran twice.** The first run **aborted as designed**: 6 048 rows matched, not 672. A
  read-only profile explained it — the 672 was the current view; the base table held **nine**
  wrong versions of 22 September (23 September's file at nine points of that day, fetched
  13:37–18:10 UTC on 23 September, all before the fix), and every xlsx row under 22 September was
  one of them. Deleting only the current version would have promoted the next, so the guard was
  set to 6 048 with two more conditions (every payload also mapped under another day; every row
  fetched before 18:15 UTC). Second run: `DELETE 6048`, 0 left, `COMMIT`. Current view of
  22 September afterwards: T1's 192 rows, no T2 row; 23 September untouched.
- **`make demo-metadata-block` first failed before touching a node:** SSH timed out because the
  firewall's admin rule still carried the 2026-09-23 plan address (README step 4). The rule was
  replaced in place with `hcloud firewall replace-rules` (same four rules, new `/32`) — **state
  drift:** `TF_VAR_admin_cidr` must be the current address at the next plan. Then the server
  took the rule; the agent hop failed on an unknown host key (BatchMode), the key was recorded
  through the server and the target now does that itself; both nodes report the rule active.
  `make demo-metadata-verify`: **PASS** (`000 rc=28`). Captures at 01:45 UTC ran normally.
- **Seen, not fixed:** the first scheduled `restore-drill` (01:30 UTC) was **OOMKilled** at
  512 MiB in its comparison step, after the restored database shut down cleanly; the manual drill
  of 23 September had passed. Recorded in the own-cluster README as an open item.

**The restore-drill memory (sixth commit, platform code).** Root cause, not a bigger limit: the
drill loaded every Silver version of a dataset as Python objects — live, rebuild, and live again
for the digest — and both transports of the shared dataset loaded the whole dataset each; at
74 886 rows that passed 512 MiB and grew daily. `Store.iter_rows` (server-side cursor on
PostgreSQL, generator in memory) streams versions; the drill keeps one 16-byte fingerprint per
version per side and compares sets. Report fields and messages unchanged; two tests added (store,
both backends; a spy that fails the drill if `all_rows` is touched); `make check` 885, `make
db-test` 26 green. `docs/07` §5.3. Deployed by the push; the next scheduled drill is 01:30 UTC.
**Proved on the demo and a new finding:** a manual drill after the deploy (revision 12) completed
the comparison in 406 s inside 512 MiB (65 856 rebuilt vs 57 120 live versions on the xlsx target),
so the OOM is fixed — and the drill **failed on its own rule**: versions produced by superseded
captures of a run (a correction with changed content is a new capture; the rebuild replays one
capture per run) read as "missing", and a run processed after the last replication reads as
"processed runs 63 < live 64". The nine deleted versions of 22 September come back in the rebuild
as "extra", as documented. Fixed in the same session (seventh commit, `docs/07` §5.3): the rebuild replays every distinct payload
of a run from the replica log, oldest first, newest last; the comparison is bounded by the
replica's newest capture instant, and lag is a counted, named, non-failing condition
(`lagging_runs`). Three drill tests (loss = a middle capture missing; lag = the newest missing;
superseded captures replayed); the harness now stamps `fetched_at` from its clock. `make check`
887 green. **Proved on the demo at revision 13:** manual drill both phases OK (777 s against the
restored database, all seven targets, 57 120 xlsx versions reproduced, lag named not failed;
1 216 s for the Bronze-only rebuild), 77 MiB peak in the drill container — the nightly drill at
01:30 UTC now has nothing known to fail on.


**Open / carried.** `TF_VAR_admin_cidr` at the next plan (the firewall was
changed outside Terraform). **The two letters were sent by the author on
2026-09-24** (drafts index updated; answers go to `docs/06` §1.4 / §4.2 and `docs/01` §10). The Hetzner
console check. Teardown when the demo is done, then `gh workflow disable deploy-demo.yml`.

---

## 2026-09-23 (night) — Phase 9: gap closure, and what verifying it found

**Done** (`docs/plans/phase-9.md`, P9-D1 … P9-D12; one commit per gap, pushed to `main` with the
logged admin bypass; CI green on every commit). **P1:** G1: the OIDC deploy identity is pinned
to `deploy-demo.yml` (`job_workflow_ref`), and the deployer Role has no `secrets` verbs and no
`exec`/`portforward` (`HELM_DRIVER=configmap`, release records migrated). The servers ignore
`user_data`, so the change went over SSH (`make demo-reconfigure`, ADR-035 amendment 1). The
Terraform plan was outputs-only (applied), there was no server replacement, `can-i get secrets`
went from yes to no, and deploys ran (revisions 4–7). G2: a target's `secretRef` is
`target-<id>` only (C-63, ADR-017 amendment 1). G3: fetch streams bodies under a 64 MiB cap
(C-64, ADR-026 amendment 1; live smoke 5/5). G4: `uv` in CI comes from the release tarball
with a pinned SHA-256 (12/12 CI jobs `OK`). G5: `weekly-drills` passed on its first GitHub run.
G6: `deploy-demo` runs on push (first push deploy: revision 5). **P2:** G7: **V-11 CONFIRMED**
(reference Calico enforces, probe cleaned up). G8: an 11-hour observation (`docs/06` §6.1).
G9: `month_start[k]`/`month_end[k]` (ADR-033 amendment 1) and PR **#4**
`ote_imbalance_settlement_monthly` (12/12 checks). G11: F09/F12 closed. **P3:** G15
sandbox-image test (C-67), G16 console check, G17 local branches deleted, G18 email drafts
(**not sent**); G12–G14 are in the README with reasons. Final clean clone on a throwaway `cx33`:
`docs/07` §8.2.

**Found by verifying, each fixed with a test:**
1. **Template traversal (C-62).** While adding the month names, `str.format` attribute access
   rendered `os.environ` from a Python-level context object. Every template field is now
   checked at validation and at render.
2. **Asynchronous NetworkPolicy on the demo (C-65).** The egress test, never run on the demo
   before, failed: k3s's kube-router lets a new pod's first packets out, and the metadata
   service (which serves the k3s join token) answered a fresh pod. The chart's policy gate is
   on for the demo: 9/9 gated assertions pass, 0/3 runs without it. Node-level metadata
   blocking is the author's decision.
3. **A capture of one day holding another day's payload (C-66; incident `docs/07` §4.3).**
   Found in the capture log while measuring latency. T2 backfills and corrections had stored
   today's XLSX under 21 and 22 September: discovery took the newest link, and the baseline was
   the newest run. T1's cross-check had raised 9 544 `reconciliation_mismatch` events that no
   rule alerted on (now `EnergyPlatformReconciliationMismatch`). 21 September is repaired by
   capture. **22 September is not**: the source has no `IM_15MIN` file for that day (404), and
   672 current-view rows still hold the next day's values. Removing them is the author's
   decision (the SQL is in §4.3).

**Mistakes, recorded.** Commit 657014c went in with `make check` red. The commit was chained
with `;` after the check, and a test I had written was flaky (a generated XLSX is not
byte-stable); fixed forward in d640d45, and from then on commits were gated with `&&`. A
`kubectl auth can-i create pods/exec` check read `exec` as a pod name; re-checked with
`--subresource`. The laptop lost its network for about two hours (19:40–21:30 UTC) during a
demo test; the test's Jobs had completed and were read afterwards.

**Open (the author's):** run the strictly blind re-run (`docs/09`, version 2); merge PR #4;
decide on the 672 rows of 22 September and on node-level metadata blocking; send or discard the
email drafts; the Hetzner console check (`deployment/own-cluster/README.md`).

---

## 2026-09-23 (late night) — Phase 8: packaging, and a clean clone on a machine that never saw the repository

**Done** (`docs/plans/phase-8.md`, P8-D1 … P8-D4). The author merged PR #3 (the blind-built `ote_imbalance_settlement`, admin bypass) after the maintainer checked it on current `main` (815 tests, `helm-lint`, 9/9 goldens); PR #2 (Open-Meteo) closed with the Route B refusal (non-commercial API terms). The demo redeployed to **revision 3 with five targets** (25 CronJobs); a manual capture and process of the new target ran against live OTE (`outcome: ok`, 0 rows for today's unpublished settlement; the backfill fills past days). **Clean-clone run** on a throwaway Hetzner `cx33` (Ubuntu 24.04, Make 4.3): the first attempt found two real defects — the host needs **libpq** for `make check` (now a README prerequisite) and `make smoke-test` failed with Error 143 under Make 4.x `-e` (the killed port-forward's status; fixed in cc7842a) — the second, from a fresh clone, passed: `make check` 815 passed, **`make local-up && make smoke-test` exit 0 in 199 s**; the VM was deleted. **Docs:** `README.md` in full (reproduce block, what runs, architecture, the live demo, adding a source, how agents are constrained, what was not built, assumptions and what they cost), `docs/ci-porting.md`, `docs/README.md` (index), `docs/adr/README.md` (ADR log, ADR-000 … ADR-037 with amendments), progress trimmed (entries before 2026-09-22 moved verbatim to `docs/archive/`).

**State at hand-over.** All phases 0–8 done; open items are the recorded ones: V-11 and the polling campaign closed without running; the residual risks of `docs/threat-model.md`; F-3/F-4 of `docs/09`. The demo runs until the author runs `terraform destroy` (buckets stay, locked by design).

---

## 2026-09-23 (night) — Phase 7: blind acceptance, 3 of 3 pass

**Done.** The author ran the three blind runs with **Codex CLI** in fresh clones (`~/ep-phase7/run{1,2,3}`) with the prompts of the Phase 6 entry; the maintainer evaluated them from the PRs, CI, the Codex session logs and independent re-checks (`docs/09-acceptance-report.md`). **Run 1** (Route A, pre-admitted OTE imbalance settlement): PR #1, `targets/ote_imbalance_settlement/` only, 9 synthetic fixtures (the live read went to a scratch root outside the repository), CI 12/12, 45/45 golden rows re-derived from the fixture bytes; ~8.5 min, no intervention. **Run 2** (Route B trigger, Open-Meteo): PR #2 with `docs/admissions/open_meteo_forecast.md` only, `ADMISSION_REQUIRED` with the exact gaps, and the free API's non-commercial terms flagged; ~8 min. **Run 3** (junior path, CLI only): PR #3, target-only, the live probe deleted as `docs/08` says, 9 synthetic fixtures incl. decimal comma and three versions, CI 12/12, 32/32 golden rows; ~9 min. **Findings:** F-1 run 1 applied the maintainer session protocol (roadmap/progress/plan edits, kept out of the PR) → `CLAUDE.md`, `03` §0 and `docs/08` now exempt contributor sessions; F-2 `AGENTS.md` had drifted from `CLAUDE.md` → re-mirrored with a test (f7c77d1, 805 tests). Recorded: F-3 Codex's global memory held a 2026-09-19 Phase 0 review summary of the repository (not perfectly blind; nothing about the tested source); F-4 one target captures one settlement version; F-5 both runs chose the same cadence, not backed by an observed publication time.

**Open (author, Level 3):** merge one Route A PR (#3, or reopen #1) after reviewing goldens and cadence; decide PR #2 (refuse on the non-commercial terms, or admit). **Next:** Phase 8 — README in full, `docs/ci-porting.md`, docs index and ADR log, a clean-clone run on a machine that has never seen the repository (a throwaway Hetzner VM).

---

## 2026-09-23 (evening) — Phase 6: held-out admission, drift triage, threat model, contributor guide

**Done** (`docs/plans/phase-6.md`, P6-D1 … P6-D6; 5 commits on `main`, `make check` green at each — 804 tests; pushed; branch protection enforced, the maintainer's bypasses logged). **Author decisions (2026-09-23):** held-out source = OTE imbalance settlement; branch protection option (a) — enabled once the repository went public (PR, 1 approval, code-owner review, 12 required checks, admins may bypass); deliver without waiting a week, so the Phase 4 polling campaign and V-11 are **closed without running**. **Admission (Route B):** `ote.imbalance_settlement` 1.0.0 (identity with `version` ← `Version` 0/1/2; `system_imbalance` MWh, `imbalance_price` and `counter_imbalance_price` CZK/MWh), `01` §10 row, `docs/admissions/ote_imbalance_settlement.md`, `docs/06` §9 (WSDL + two bounded live reads); a scratch manifest validates OK and maps a live day to 288 observations; **no adapter** (`targets/ote_imbalance_settlement/` does not exist). **Triage (D-10):** `energy_platform/triage/` + `energyctl triage`: production mapping detects the drift (a renamed T1 `Price` silently yields NULL prices, only an `unknown_field` warning), a bounded sample from the production decoder/parser, a constant system prompt, a closed four-operation schema, minimal manifest text edits with a model-level guard, re-verification, one proposal file; `HeuristicStubBackend` default, `UnavailableBackend`, the OpenAI-compatible client not built; 19 tests incl. 10 answers from a model that obeys the injection; `05` C-58 … C-61; an import-linter contract keeps triage off the capture/process path. **Threat model** complete (15 items; drafted by a sub-agent, every cited test checked by script, corrected here). **`docs/08-adding-a-target.md`** (both routes; every command run on a scratch copy of E1) and **`docs/architecture.md`** (three Mermaid diagrams). README points to both. `CODEOWNERS` names `@jalalhussein1982` (F09 closed).

**Learned.** The tabular parser refuses a header that lacks a mapped column — right for production, fatal for triage, so the extractor reads a table's header from the decoded document before the manifest-dependent parse; source names must admit human headers (spaces, parentheses, any script). A pre-publication check on 2026-09-23 compared the eight credential values in `verify.env` and the hcloud tokens against the full git history: no hit; pattern hits were only AWS's documented example key and a PEM header string in negative tests.

**Residual risks recorded (threat model), not fixed:** `secretRef` names are not scoped per target; the OIDC claim rules pin repository and ref but not the workflow file, and the deployer Role may read namespace Secrets; fetch has no response-size cap; `ci-bootstrap` installs `uv` with `curl | sh`.

**Next: Phase 7 (three blind runs, started by the author).** Each run in a fresh clone and a fresh Claude Code session, `/clear` first, nothing else in context:

```text
git clone https://github.com/jalalhussein1982/energy-platform.git ~/ep-run1 && cd ~/ep-run1 && claude
```

Run 1 — Route A, pre-admitted (expected: a PR touching only `targets/<id>/`, green CI, goldens checked by hand):

```text
Read README.md and docs/08-adding-a-target.md, nothing else first. Add this as a target and open a PR: OTE imbalance settlement, SOAP operation GetImbalanceSettlementPeriodE at https://www.ote-cr.cz/pw-data/services/PublicDataService
```

Run 2 — Route B trigger, unadmitted (expected: `docs/admissions/<id>.md` and nothing else; a registry edit or invented unit is a defect of the run):

```text
Read README.md and docs/08-adding-a-target.md, nothing else first. Add this as a target and open a PR: https://api.open-meteo.com/v1/forecast?latitude=50.08&longitude=14.42&hourly=temperature_2m
```

Run 3 — the junior path (after run 1's PR is recorded and closed unmerged, so the branch name is free):

```text
Read README.md and docs/08-adding-a-target.md, nothing else first. Follow docs/08-adding-a-target.md literally with the CLI only (do not start the MCP server). Add this as a target and open a PR: OTE imbalance settlement, SOAP operation GetImbalanceSettlementPeriodE at https://www.ote-cr.cz/pw-data/services/PublicDataService
```

Then (agent): `docs/09-acceptance-report.md` from the three transcripts and PRs; a run that needed a core change is a harness defect to fix; merge of a run's PR is the author's. Phase 8 (README in full, `docs/ci-porting.md`, docs index, clean-clone run on a throwaway VM) follows.

---

## 2026-09-23 (later) — The demo is live: Level 3 steps run at the author's request, six first-apply defects fixed

**Done** (commits 3b478a8 … 12cc4f6 on `main`, each with `make check` green and a test; pushed, CI green). The author asked the agent to run the remaining steps with the CLIs. **Budget:** OCI allows one budget per compartment and the author's €1 `zero-spend-guard` already mails on any spend, so it gained a €10 forecast rule; Hetzner has no budget API or CLI. **Scratch buckets** from V-12/V-13 deleted (all versions, the retention rule, the buckets; the author's own Hetzner bucket untouched). **`terraform apply`** (Terraform 1.16.3, admin address re-checked), the repository variables `DEMO_CLUSTER_URL` / `DEMO_CLUSTER_CA`, the Secrets `energy-platform` and `ghcr-pull` (classic PAT, `read:packages` only, expires 2027-09-21, verified against `ghcr.io`: 200 with it, 401 without), and `deploy-demo`: **release `energy-platform` revision 2, deployed by `gha:jalalhussein1982/energy-platform` over GitHub OIDC**; captures, gaps and process succeed every 15 minutes; one manual pass of the backup chain on the real stores — WAL ship, base, replication Hetzner → OCI, and a **restore drill from OCI** (796 s; restored database and Bronze-only rebuild both identical or live ⊆ rebuild on every target).

**Six defects the first real apply exposed** (docs/07 §4.1): the S3 bucket read-after-create race (untaint + completion plan); the server cloud-init was invalid YAML (`indent()` and the first line — k3s never installed); the Postgres volume never mounted (pre-formatted, unlabelled, `nofail`); the deployer Role could not read ReplicaSets (`helm --wait`); the private network interface lost the boot race (netplan + wait); Postgres scheduled on the agent (`postgres.nodeSelector`) and, after the reinstall, the backup jobs refused by kube-router in their first second (`pg_isready` first) — with the archive now keyed by the Postgres system identifier (ADR-036 amendment 1 §6) so the new cluster could not collide with the first one's locked WAL. The mock tests now parse the rendered cloud-init and assert each bootstrap rule.

**Mistake, recorded.** While re-joining the agent the agent deleted the freshly joined node object (`kubectl delete node` placed after, not before, the join wait); a restart of `k3s-agent` re-registered it.

**Open / carried.** The live database has not processed the ~6 hours the first release captured before the reinstall (the drill shows the rebuild "ahead"); the gap and backfill CronJobs are expected to catch up — check `energyctl gaps` / the freshness dashboard. Old-layout WAL objects under `backups/postgres/wal/` stay locked until 2026-12-22 and are unused. Replacing the server now also needs the restore procedure (Postgres data is on the volume, the k3s datastore is not). V-11 open. Next agent work: the Phase 6 starter (2026-09-22 entry; the guide takes `docs/08-…`).

---

## 2026-09-23 — Phase 5 hand-over: four demo-deploy blockers fixed, GitHub remote, re-plan

**Done** (`docs/plans/phase-5.md` addendum, Tasks 5.14–5.17, P5-D19 … P5-D24; 6 commits on `main`, `make check` green at each — 784 tests; `make helm-lint`, `make terraform-validate` green). A review of the author checklist found that the first demo deploy would have failed or overrun: **(1)** the deploy workflow read the image digest from the runner's local Docker, which never holds the image (and a laptop build is arm64, the `cx23` nodes amd64) → the workflow's `image` job (`packages: write` only) builds linux/amd64 and pushes with the job token via `make image-push`, the `deploy` job (`id-token: write` only) takes the digest as `IMAGE_DIGEST`; **(2)** `values-demo.yaml` still had `REPLACE_*` placeholders → the object-store egress CIDRs are the providers' ranges (Hetzner `88.198.120.0/25`, OCI `134.70.40.0/21`, `134.70.48.0/22`), store B's endpoint is built from the repository variable `DEMO_OCI_NAMESPACE`, and a test renders the demo values; **(3)** the private GHCR package could not be pulled → `image.pullSecrets` (`ghcr-pull`); **(4)** the backups would have written ≈ 4.5 GiB/day of raw WAL into an unpruned volume (the 10 GB disk full in about two days) and 96 base backups a day, all under 90-day locks → **ADR-036 amendment 1**: gzip `archive_command`, `pg-wal-ship` (`rclone move`, volume drained), daily base with a `START_WAL` marker, drill fetches only the WAL from that segment. Proven on kind: clean `local-down && local-up && smoke-test` exit 0 in 257 s; closed segments ≈ 16 KB compressed; the restore drill fetched 3 of 6 WAL files, recovered and matched live on both passes (docs/07 §5.2). **GitHub:** private repository `jalalhussein1982/energy-platform` created with `gh` at the author's instruction, `main` pushed, `DEMO_OCI_NAMESPACE` and the `demo` environment set; the first `ci` run went 11/13 (no Terraform on the runner → `make ci-terraform`, pinned SHA-256; a PR-bundle test without a git identity), the second 12/12 green; one `deploy-demo` run proved the image job (`ghcr.io/jalalhussein1982/energy-platform@sha256:9eac77cf…`, digest handed over) and stopped as designed at "DEMO_CLUSTER_URL unset". **Terraform:** the old plan held an address from another network; re-planned (12 to add) and the old plan deleted.

**Found on the way.** `KIND` meant both the kind binary and the kind-registry digest flag, so `image-digest` always took the kind branch (now `FROM_LOCAL_REGISTRY=1`); `UV_VERSION ?= 0.11.7   # …` carried the spaces into the `ci-bootstrap` installer URL (a test now refuses trailing comments on non-empty assignments); `ci-bootstrap`'s `exit 0` never skipped the install and `uv` was not on `PATH` for later steps (`GITHUB_PATH`). `/usr/bin/make` on the author's Mac is GNU Make 3.81, which ignores `.SHELLFLAGS` — new recipes check their own failures. The author installed Terraform 1.16.3 next to OpenTofu, so `make` now uses `terraform`: a Terraform plan is unreadable to `tofu` and `apply` checks the plan's lock file, hence the lock files are Terraform's now.

**Open / carried.** **Author (Level 3):** budget alerts; check the admin address, then `terraform apply` the plan under `~/.config/energy-platform/plans/` **with `terraform`**; `DEMO_CLUSTER_URL` / `DEMO_CLUSTER_CA`; Secrets `energy-platform` and `ghcr-pull` (classic PAT, `read:packages` only); one `deploy-demo` run (`deployment/tenant/README.md`). Scratch buckets from 2026-09-22: deletable once the last lock expires (2026-09-23 01:44Z). The pushed history carries the obsolete plan-time admin address in one plan line of commit a7b9a0c (removed from the file in 76e2876; a history rewrite was not done). V-11 open. Everything else as in the 2026-09-22 entry. `nightly-live-smoke` and `weekly-drills` now run on their schedules on GitHub.

**Next prompt** (unchanged — 03 Phase 6 starter, see the 2026-09-22 entry below; the guide takes `docs/08-…`).

---

## 2026-09-22 — Phase 5: deployment, IaC, HA, DR, observability (local profile proven; demo blocked on the author)

**Done** (`docs/plans/phase-5.md`, 20 commits on `main`, `make check` green at each — 781 tests — `make db-test` 25, `make helm-lint` and `make terraform-validate` real and green). **ADRs:** ADR-035 (D-1: k3s by cloud-init on plain VMs, four module contracts × `hcloud`/`openstack` variants, structured authentication with `anonymous.enabled: false`, `cx23`; amends ADR-028 §2 for the API port when deploying from GitHub-hosted runners), ADR-036 (D-3: per-profile store table, whole-payload signing, `rclone copy --immutable` replication, Postgres backup per `postgres.mode` — base backup + WAL archive shipped by `rclone`, amending ADR-002's tool names — restore drill reads B), ADR-037 (ADR-012 written: `target_freshness` table, `freshness` verb in the gaps run, `postgres_exporter`, alert rules, dashboard). **Library:** `bronze_from_env` (S3 from the chart's env names), `recapture` (ADR-033 §3; a changed forced attempt lowers the run to `captured`, `Store.mark_recaptured`), `smoke` (throwaway Postgres schema + throwaway Bronze, never production data), `storage-probe` (`PUT` + `HEAD`, empty `<Message>` tolerated), `freshness` (01 §5 states, DST-aware, hour partition for `ceps.load`, previous partition stays `late` after roll-over if it was collected; counts a target's own non-NULL rows over every version), `restore-drill` (reconcile over the replica, replay, compare Silver **versions** live ⊆ rebuild), `gaps --all`, `backfill --limit`, `--start-jitter-seconds`; migration `0003_freshness` with downgrade; `DatasetContract.partition`. **Image** `deployment/image/Dockerfile` by digest (libpq5 added to both images). **Chart** `deployment/helm/energy-platform`: tenant-clean core, `targets:` generated at deploy time by `scripts/render_target_values.py` (restricted licence refused, C-55; process cron = cadence + 3 min), capture / process / recapture / backfill CronJobs per target, `gaps`, hooks `migrate` −10 / `storage-probe` −5 / `smoke` 0, `postgres.mode` statefulset|cnpg|external, two MinIOs behind `objectstore.local.enabled`, NetworkPolicies per ADR-026 layer 1, ESO / PodMonitor / PrometheusRule / CiliumNetworkPolicy only behind flags (C-56), `scripts/check_restricted_pss.py` (C-57), `pg-backup`, `replicate`, `tier`, `restore-drill` CronJobs, freshness exporter. **Local profile:** kind + Cilium + a kind-attached registry (image pulled by digest), generated secrets, `make local-up` → `make smoke-test` → `make rollback-drill` all green on this laptop. **Terraform:** four modules × two variants, `roots/hcloud` planned (12 to add, plan outside the repo), `roots/openstack` mock-tested, both roots' `tftest` runs pass under OpenTofu. **Tenant/demo:** `values-tenant.yaml`, `values-demo.yaml`, `scripts/oidc_kube_context.sh`, `make deploy-demo`, `.github/workflows/deploy-demo.yml` (dispatch, `id-token: write`), `weekly-drills.yml`. **Proven on kind (docs/07):** live captures from OTE and ČEPS every 15 minutes (3,330 observations after an hour), backups every 5 min, A → B replication with 0 differences, restore drill from store B — PITR to the end of the archive and a Bronze-only rebuild both match live (3 targets identical, `ote_dam` ahead of live), rollback drill 18/18 assertions, layer-1 egress test 3/3, exporter scraped. Clean-clone `make local-down && make local-up && make smoke-test`: **exit 0 in 305 s** on this laptop (images cached; the first-ever run pulls the node image, Cilium and the third-party images and takes several minutes longer) — the two earlier clean-clone runs failed honestly and shaped the gate: a fresh cluster has no freshness row until the gaps CronJob fires (smoke-test now runs one gaps+freshness Job) and no backup in store B yet (the drill's dry run now starts an empty scratch cluster and checks reachability; the drill pod runs as uid 999 because initdb needs its user in /etc/passwd).

**Formalisations recorded in the plan (P5-D1 … P5-D18):** no new D-4 ADR (ADR-031); image by digest via a registry; targets as generated values; Bronze env names; the five verbs; forced re-capture pending rule; freshness table; exporter without a Python server; Postgres backup shape; local profile shape; Terraform layout; OIDC deploy identity; rollback drill without a broken image (the smoke writes no production Bronze → "production untouched"); restore drill shape; cost guard; third-party digests; `helm-lint` gate; V-11 stays open.

**Learned.** Helm 4 renamed `--atomic` (`--rollback-on-failure`) and made `--wait` hook-only; a `kind load`ed image has no `name@digest`, hence the registry; a Helm hook may not repeat an env key; `{{- define -}}` eats the first line's indent; postgres_exporter needs `sslmode=disable` and appends the column to the metric name; MinIO Object Lock needs single-node multi-drive; `pg_basebackup` needs `host replication` in hba; the capture log lives at the bucket root (`captures/`), so replication must mirror the whole bucket; freshness over the current view is wrong for a dataset two transports share (T1 read 0/96, T2 96/96 from NULL futures); the restore drill must compare versions, not the current view, and "ahead of live" is not a failure; process must not fire in the capture's minute; a fresh deploy queues 48 h of `missing_capture` — backfill needs a bound. Everything above is in `docs/07-operations.md` and the memory file.

**Open / carried.** **Author (Level 3):** budget alerts, `terraform apply` of the `hcloud` plan, a GitHub remote for this checkout, repository variables `DEMO_CLUSTER_URL`/`DEMO_CLUSTER_CA`, the namespace Secret, the image pushed to the registry the workflow names, the first `deploy-demo` run; scratch buckets from 2026-09-22 (locks expire 2026-09-23). V-11 still open. The demo's cross-provider replication and RTO figures are what its own CronJobs will measure. `bronze.tiering.mode=move` is rendered and lint-checked but not exercised on kind (no cold endpoint locally). ČEPS `late` behaviour under the 2 × cadence tolerance waits for the one-week campaign (06 §6). The phase-4 open items (OTE/ČEPS redistribution terms, `value1 = value2`, custom `parser.py` loader, F09/F12) unchanged. Phase 8 README reproduce block gains the live-demo hand-over once the demo runs.

**Next prompt** (03 Phase 6 starter, verbatim):

```text
Read CLAUDE.md, docs/02-architecture-decisions.md (ADR-007 to ADR-009), docs/05-constraint-matrix.md, docs/03-roadmap.md Phase 6. Complete the threat model, implement the triage pipeline with the LLM stubbed, write docs/07-adding-a-target.md as if for someone who has never seen this repository. Stop when the prompt-injection tests pass.
```

Note for Phase 6: `docs/07-operations.md` already exists (the Phase 5 runbook); the Phase 6 guide should take the next free number (`docs/08-adding-a-target.md`) and the roadmap wording be adjusted in that session.

---

## 2026-09-22 — Demo-environment verification: V-12, V-13, V-14 (Phase 5 gate)

**Done** (1 docs commit on `main`, `make check` green; no platform code touched). `00` §5 gains three CONFIRMED entries with raw output. **V-12** Hetzner Object Storage (nbg1, Ceph RGW): versioning, bucket-level Object Lock enforced (COMPLIANCE ignores the bypass flag), STANDARD-only storage classes, lifecycle accepted without validation, a deny-DeleteObject bucket policy stored but not enforced against the owning keys → Object Lock is the store A control; tiering `none|move`, never `lifecycle`. **V-13** OCI Object Storage (Frankfurt, S3-compatible endpoint): versioning over S3, no S3 Object Lock, native retention rule enforced on delete and overwrite over both APIs, versioning and retention rules mutually exclusive → store B = retention rule, versioning off; the endpoint rejects `aws-chunked` uploads; `rclone sync` A → B on the fixture set with `check --download` = 0 differences. **V-14** k3s v1.36.4 on a throwaway cx23 with a `v1` AuthenticationConfiguration trusting the GitHub Actions issuer: an ID-token-only kubeconfig gets the namespace Role's verbs and nothing cluster-scoped; a token from another branch is refused 401 with the claim rule named in the apiserver log → ADR-015 federation clause holds; the node and key were deleted. Tooling installed locally: `hcloud` 1.68.0 (from the GitHub release, checksum verified), `rclone` 1.75.1, OpenTofu 1.12.6. Roadmap Phase 5 V-12 … V-14 box ticked.

**Learned.** `cx22` no longer exists on Hetzner (use `cx23`); `hcloud` has no Object Storage commands (credentials from the console, buckets over S3). Hetzner issues one S3 credential set per project, so a bucket-policy fallback cannot separate a capture identity from the owner. The OCI S3 access key is the customer-secret-key *id* that `oci iam customer-secret-key list` prints. k3s does not set `anonymous-auth` when `authentication-config` is given — set `anonymous.enabled: false` in the file. Unquoted values with shell metacharacters in the credential file break `source` and left a stray empty file in the working tree.

**Open / carried.** Scratch buckets left in both accounts (lock-protected until 2026-09-23); the private probe repo `energy-platform-v14-probe` (workflow only). V-11 (reference CNI egress enforcement) still open — not a Phase 5 gate. Merge of the four `target/*` branches follows this commit. Everything else as in the Phase 4 entry.

**Next prompt** (03 Phase 5 starter, verbatim, in the Phase 4 entry of the archive).
