# Plan — Phase 8: Submission packaging (2026-09-23)

| | |
|---|---|
| Goal | "README reproducible by a stranger" (`03` Phase 8): the README in full, the CI-porting note, a docs index and a complete ADR log, a trimmed progress log, and one clean-clone run on a machine that has never seen the repository. |
| Spec | `docs/03-roadmap.md` Phase 8; ADR-010 (local reproduction), ADR-015 (CI as a thin wrapper); `00` §2 (assumptions register), `02` §4 (defaults not implemented). |
| Do not | Edit `docs/00`, `01`, `02` (frozen); leave the throwaway VM running; claim a reproduction that was not run. |

## Decisions

| # | Decision | Why |
|---|---|---|
| P8-D1 | The clean-clone run is a **throwaway Hetzner `cx33`** (4 vCPU, 8 GB, Ubuntu 24.04, x86) in the demo project, created and deleted with `hcloud`, SSH key-only: install Docker, kind, helm, kubectl, uv and make at the Makefile's pinned versions, `git clone` the public repository, run the README's reproduce block verbatim, record the wall clock and the result, delete the server. | "A machine that has never seen the repository"; cents of cost; no change to the demo's Terraform state. |
| P8-D2 | The ADR log is `docs/adr/README.md` (ADR-000 … ADR-013 live in `02`, which is frozen; ADR-014 … ADR-037 are files); the docs index is `docs/README.md`. | `02` may not be edited in a task. |
| P8-D3 | "Progress log trimmed": `docs/progress.md` keeps an at-a-glance table and the entries from Phase 5 on; the earlier entries move verbatim to `docs/archive/progress-2026-09-19-to-20.md` (nothing deleted). | Readable log, full audit trail. |
| P8-D4 | The live demo is redeployed so the fifth target (added blind in Phase 7) runs there; the README's hand-over section describes the demo as it is. | The extension path shown end to end. |

## Tasks

- [x] 8.1 Redeploy the demo (`deploy-demo`) with five targets; confirm the imbalance-settlement CronJobs run.
- [x] 8.2 Clean-clone run on the throwaway VM (P8-D1); record in `docs/07-operations.md` §8.
- [x] 8.3 `README.md` in full; `docs/ci-porting.md`; `docs/README.md`; `docs/adr/README.md`; progress trim (P8-D3).
- [x] 8.4 Roadmap Phase 8 ticks; progress entry; commit and push.

## Acceptance

The README's reproduce block passes verbatim on a machine that has never seen the repository;
every document the README links exists; `make check` green.
