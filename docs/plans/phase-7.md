# Plan — Phase 7: Blind acceptance tests (2026-09-23)

| | |
|---|---|
| Goal | Three blind runs per `03` Phase 7 and ADR-022 §3; `docs/09-acceptance-report.md`; defects fed back and closed. |
| Runs | Started by the author in fresh clones and fresh agent sessions with the prompts of `docs/progress.md` (2026-09-23 evening); the maintainer (agent) only evaluates. |
| Do not | Help a run; merge a run's PR (Level 3); change the harness to make a run pass. |

## Tasks

- [x] Run 1 (Route A, pre-admitted), run 2 (Route B trigger), run 3 (junior path, CLI only) — executed by the author with Codex CLI.
- [x] Evaluate each from the PR, CI and the session log; re-check manifests, fixture provenance and every golden row independently.
- [x] Findings F-1 (contributor sessions and the maintainer protocol) and F-2 (`AGENTS.md` drift) fixed with a gate — commit `fix(docs): …`.
- [x] `docs/09-acceptance-report.md`, roadmap ticks, progress entry — commit `docs(phase-7): …`.

## Acceptance

All three runs meet `02` §5 criterion 4 (ADR-022) without a core change or guidance; findings closed or recorded.
