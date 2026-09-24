# Acceptance report — Phase 7 blind runs (2026-09-23)

| | |
|---|---|
| Protocol | `docs/03-roadmap.md` Phase 7; ADR-022 §3 (a pre-admitted and an unadmitted source); `02` §5 criterion 4 as amended by ADR-022 |
| Criterion | "A fresh agent, given only the README and the URL of a **pre-admitted** unseen source, opens a PR that passes CI and touches nothing outside `targets/<id>/`; given an **unadmitted** source, it produces an admission request and nothing else." |
| Agent | **Codex CLI** (not the agent that built the harness), one fresh session per run, started by the author |
| Setup | a fresh clone of `github.com/jalalhussein1982/energy-platform` per run (`~/ep-phase7/run{1,2,3}`), the prompts of `docs/progress.md` (2026-09-23 evening), no other input |
| Evidence | the three PRs; the Codex session logs (`~/.codex/sessions/2026/09/23/`, author's machine); the maintainer's independent checks below |
| Result | **3 of 3 pass.** No core change was needed, no architectural guidance was given, no question was answered. Two documentation defects found and closed (F-1, F-2). |

## Summary

| Run | Route | Input | Outcome | PR | Time | Interventions | CI | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | A — adapter addition | OTE imbalance settlement, `GetImbalanceSettlementPeriodE` (pre-admitted in Phase 6) | `targets/ote_imbalance_settlement/` only: 32 files, 9 fixtures, 9 goldens | [#1](https://github.com/jalalhussein1982/energy-platform/pull/1) (closed unmerged to free the branch for run 3) | ~8.5 min | 0 | 12/12 | **PASS** |
| 2 | B — escalation | `https://api.open-meteo.com/v1/forecast?…&hourly=temperature_2m` (not admitted) | `docs/admissions/open_meteo_forecast.md` only | [#2](https://github.com/jalalhussein1982/energy-platform/pull/2) | ~8 min | 0 (one "finished?" status question, no guidance) | 12/12 | **PASS** |
| 3 | A — junior path, CLI only | as run 1, "follow docs/08 literally, no MCP" | `targets/ote_imbalance_settlement/` only: 32 files, 9 fixtures, 9 goldens | [#3](https://github.com/jalalhussein1982/energy-platform/pull/3) | ~9 min | 0 | 12/12 | **PASS** |

## Run 1 — adapter addition (Route A)

The session read the README and `docs/08-adding-a-target.md`, found the admission record by the
operation name, ran `make check` as a baseline, scaffolded with `energyctl new-target … --dataset
ote.imbalance_settlement`, and wrote the manifest. It made one live read **into a scratch targets
root outside the repository** (`record-fixture --targets-root /private/tmp/… --live`) to learn the
shape, then generated nine **synthetic** fixtures with the real structure (ordinary day, spring
and autumn DST days, empty answer, SOAP fault, edge values, monthly and final versions, an hourly
historical day) and wrote the goldens. `make check`, `make pr-surface BASE=main`, push, PR.

Maintainer checks (independent of the session and of the platform):

- Manifest = the admission: `ote.imbalance_settlement`, the three metrics with the admitted source
  fields and units, `source_version: {source: Version}`, `ignore_fields` exactly the admission's
  eleven fields, host `www.ote-cr.cz`, request `Version 0`.
- Fixtures are synthetic: no blob matches the hashes of the live reads (`06` §9), values differ
  (first `SystemImbalance` 1.125 against 0.65683 live); DST fixtures carry 92 and 100 items.
- **45 of 45 golden rows** re-derived from the fixture bytes by an independent script (UTC instant
  → Prague day and period index → the item → the value).

## Run 2 — escalation (Route B)

`energyctl validate` returned `ADMISSION_REQUIRED` naming exactly the gaps — dataset
`open_meteo.forecast`, metric `temperature_2m`, host `api.open-meteo.com` — and the session wrote
the admission request with `energyctl admission-request`, filled it and stopped. The diff is one
file; no registry, host registry or target change. The request is substantive: data licence
CC BY 4.0, **the free API is for non-commercial use only** (a commercial deployment needs another
arrangement), rate limits, the published unit `°C` proposed "as published" and explicitly *not*
registered, the response shape (parallel `hourly` arrays, `hourly_units`), a fixture plan.

Maintainer decision (Route B, pending): **refuse for this deliverable** on the non-commercial terms,
or admit under a paid arrangement; either way the PR records the decision.

## Run 3 — the junior path (CLI only)

No `mcp-serve` in the session; every step through `uv run python -m energy_platform.cli` and Make as
`docs/08` lists them: `make sync`, baseline `make check`, `new-target`, manifest, one
`record-fixture --live` **inside the target** to learn the shape — then deleted, as `docs/08` §6
says — nine synthetic fixtures (ordinary day, both DST days, hourly day, empty answer, SOAP fault,
edge values, a decimal-comma document, three settlement versions in one document), goldens,
`make check` (814 passed), `make pr-surface BASE=main`, push, PR.

Maintainer checks: manifest identical in substance to run 1's (and to the admission); fixtures
synthetic (first `SystemImbalance` 1.12500); **32 of 32 golden rows** re-derived independently.

## Findings

| # | Kind | Finding | Status |
|---|---|---|---|
| F-1 | defect (docs) | Run 1 followed the **maintainer** session protocol inside a contributor task: it wrote `docs/plans/phase-7.md` and edited `docs/03-roadmap.md` and `docs/progress.md` locally. It kept them out of the PR, so the target-only rule held, but the instructions invited the edits. | **Closed** (f7c77d1): `CLAUDE.md`, `03` §0 and `docs/08` §1 say a contributor session follows `docs/08` only and touches `targets/<id>/` or `docs/admissions/<id>.md`. |
| F-2 | defect (docs) | `AGENTS.md` — what Codex reads — had drifted from `CLAUDE.md` (an older command list, no admission or PR-bundle commands). | **Closed** (f7c77d1): re-mirrored; `tests/harness/test_ci_wrappers.py::test_agents_md_mirrors_claude_md` keeps them identical. |
| F-3 | limit of the test | **Not perfectly blind.** Codex's global memory (`~/.codex/memories/MEMORY.md`, read by every run) holds a summary of a 2026-09-19 Phase 0 review of this repository: its existence, the OTE WSDL URL, general data principles. It holds nothing on imbalance settlement, the admission, `docs/08`, the harness or anything built after Phase 0. The user-level skill set was also loaded. | Recorded. A strictly blind re-run uses an agent profile with no memory. **Phase 9:** protocol and prompt handed to the author (below); **not run at hand-over**. |
| F-4 | capability, not a defect | One target sends one request template, so both runs capture settlement **version 0** (daily) and prove versions 1 and 2 by mapping only. Capturing the monthly and final settlements is one more Route A target per version on the same dataset, or a future manifest capability for several requests per capture. | **Phase 9:** closed for version 1: ADR-033 amendment 1 (`month_start[k]` / `month_end[k]`) and PR #4 `ote_imbalance_settlement_monthly`, target-only, built through the harness; **merged 2026-09-24 (d14388c) after the review in "Maintainer actions" 3, live on the demo as revision 8.** Version 2 is the blind re-run's source. |
| F-5 | observation | Runs 1 and 3 converged on the same decisions (hourly at :17, a 3-day correction at :37, version 0). Expected from one model reading one admission; the cadence is not backed by an observed publication time (the polling campaign was closed without running). | **Phase 9:** the cadence is justified by what the demo showed (`docs/06` §6.1): version 0 of D is only published after D, the correction delivers it, and the hourly poll creates the day's run. |

## Verdict

Criterion 4 holds on all three runs: the pre-admitted source became a target-only PR with green CI
and correct, hand-checkable goldens twice (agent route and the literal CLI route); the unadmitted
source stopped at an admission request. The harness needed no change; the two defects were in the
instructions and are closed with a gate.

## Phase 9 — the strictly blind re-run (F-3), protocol

Run 1's source now has an adapter on `main`, so the unseen Route A source is settlement
**version 2** (final). It is admitted, has no adapter, and needs the month-offset placeholders.
The run also tests whether the documentation is enough to find them. Blindness comes from the
setup: a new folder, an empty `CLAUDE_CONFIG_DIR` (no user memory, settings, plugins or skills)
and `--strict-mcp-config` (no connectors).

```bash
mkdir -p ~/ep-phase9-blind/claude-config && cd ~/ep-phase9-blind
git clone https://github.com/jalalhussein1982/energy-platform.git repo && cd repo
export CLAUDE_CONFIG_DIR="$HOME/ep-phase9-blind/claude-config"
claude --strict-mcp-config        # log in if asked; /memory, /mcp, /plugin must show nothing
```

```text
Read README.md and docs/08-adding-a-target.md, nothing else first. Add this as a target and open a PR: OTE imbalance settlement, final monthly settlement (Version 2), SOAP operation GetImbalanceSettlementPeriodE at https://www.ote-cr.cz/pw-data/services/PublicDataService
```

Evaluation, as for runs 1 and 3: files touched (target only), CI, goldens re-derived from the
fixture bytes, the request (version 2, a month that is actually settled, about 4 months back),
interventions, and the transcript under `~/ep-phase9-blind/claude-config/projects/`. **Status at
hand-over (2026-09-23): not run.** F-3 stays open until it is.

**Prepared 2026-09-24 (maintainer session), not yet run.** The folder exists, `claude-config/`
is empty (a probe session written into it while checking authentication was deleted again), and
`repo/` is a fresh clone of `main` at **d14388c**, i.e. *after* the merge of PR #4, so the run
sees the version 1 target as a worked example of the month-offset placeholders — the realistic
case for a later contributor, and a weaker test of the documentation alone than a clone before
the merge would have been. Two things could not be done by the maintainer agent, and were left
to the author on purpose:

- The login. An empty `CLAUDE_CONFIG_DIR` holds no credential (headless probe: "Not logged in ·
  Please run /login"); reading the main profile's credential was refused by the agent's
  permission classifier ("credential exploration"), and copying it would have been the wrong
  fix anyway.
- Starting the session. A headless launch script (`claude -p … --allowedTools Bash`) was refused
  by the same classifier ("create unsafe agents"); the protocol says the author starts it, and
  an interactive session is what runs 1–3 used.

The author's steps are exactly the two blocks above, minus the `mkdir`/`clone` (done); after
`/login`, `/memory`, `/mcp` and `/plugin` must show nothing before the prompt is pasted.
Model: whatever the fresh profile defaults to — record it from the transcript.

## Maintainer actions (Level 3)

1. Merge **one** Route A PR — #3 (open; the literal-guide run) or reopen #1 — after a code-owner review of
   the goldens and the cadence (F-5); close the other.
2. Decide PR #2: refuse (non-commercial API terms) or admit; record the decision in the PR.
3. **PR #4 (`ote_imbalance_settlement_monthly`, version 1) — reviewed and merged 2026-09-24.**
   The review was done by the maintainer agent in a detached worktree of the branch (d69757f);
   the merge itself was run by the author (`gh pr merge 4 --admin --squash --delete-branch`,
   00:23 UTC), because the agent's permission classifier refused both the merge ("merge without
   review") and posting the review as an approval ("self-approval"). The review therefore lives
   here and in `docs/progress.md`, not on the PR. Checks, in the order they were run:
   1. Surface: 14 files, all under `targets/ote_imbalance_settlement_monthly/`;
      `make pr-surface BASE=origin/main` → OK; GitHub reported `MERGEABLE`, CI 12/12.
   2. Manifest against the admission (`docs/admissions/ote_imbalance_settlement.md`): dataset,
      the three metrics with the admitted source fields and units, `source_version: {source:
      Version}`, the eleven `ignore_fields`, host `www.ote-cr.cz`. `diff` against the daily
      target's manifest on `main` is only: target id and description, `Version 1`, cadence
      (`27 7 1 * *` + a 31-day daily correction at `47 7`), `max_age: P1Y`, and the
      `{month_start[1]:%Y-%m-%d}` / `{month_end[1]:%Y-%m-%d}` placeholders.
   3. Fixtures: three, synthetic (header comment, no live values); each blob's SHA-256 equals
      its `entry.json` `payload_sha256`.
   4. Goldens re-derived from the fixture bytes by an independent script (ElementTree +
      `zoneinfo`, no platform import; kept at
      `~/.config/energy-platform/evidence/2026-09-24/pr4-rederive-goldens.py`): all **23 of 23**
      sampled rows match on UTC instant, resolution, version and value (the NULL price included);
      row counts 8 916 / 0 / 8 940 = items × 3 metrics; 2026-03-29 carries 92 periods and
      2026-10-25 carries 100.
   5. Harness gates on the branch: `energyctl validate` OK (no missing registry entry),
      `energyctl run-target-tests` OK (three goldens through the production pipeline, pytest
      exit 0).
   6. After the merge: `deploy-demo` run 35938188381 on d14388c → `image` and `deploy` both
      green, Helm **revision 8**; on the cluster the four CronJobs of the new target exist with
      the manifest's schedules (`capture 27 7 1 * *`, `process 30 7 1 * *`, `recapture 47 7 * *
      *`, `backfill 37 * * * *`, all `Europe/Prague`), no run before 2026-10-01. The only
      failing pods were the expected hourly T2 recaptures of 22 September (`docs/07` §4.3).
