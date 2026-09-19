# Plan — Review 1 remediation: Codex pre-coding verdict (2026-09-19)

| | |
|---|---|
| Goal | Close the design contradictions (F04–F08, F14) by ADR and the demonstrated gate bypasses (F02, F03, F10, F11) by code **before Phase 1 freezes contracts into code**. Gate: every accepted finding has either an ADR, a code change with a negative test, or a dated roadmap task; `make check` green. |
| Inputs | `codex-review/` (F01–F14), `docs/02` §2/§4/§5, ADR-003 rev., ADR-014, ADR-016, ADR-017, ADR-018, ADR-020, ADR-021, `docs/03-roadmap.md`. |
| Do not | Start Phase 1. Write fetch/parse/persistence code. Edit `docs/01-data-scope.md`. Rewrite accepted ADRs in place (amend by new ADR; add an "amended by" line only). Weaken a gate to make a negative test easier. |
| Frozen-doc rule | `docs/00` and `docs/02` receive only dated one-line pointers to the ADR that changes them, in the same style as the 2026-09-19 ADR-021 note. |

## Triage summary (full text in `docs/reviews/2026-09-19-codex-review-response.md`)

| Finding | Verdict | Where it is closed |
|---|---|---|
| F01 system absent | accepted, expected | Phases 1–8; no action beyond keeping README honest |
| F02 target tests not collected | accepted, demonstrated | R.8 `testpaths` + negative test |
| F03 egress lint incomplete | accepted, demonstrated | ADR-027 + R.8 banned-api, socket block, target-surface check |
| F04 blind test vs admission | accepted, design contradiction | ADR-022 + roadmap Phase 7 |
| F05 version key excludes derivation | accepted, design contradiction | ADR-023 amends ADR-018 |
| F06 capture crash window / backfill vs replay | accepted | ADR-024 amends ADR-003 rev./ADR-004 |
| F07 `helm test` is not an upgrade gate | accepted | ADR-025 amends ADR-016 §2–3, ADR-021 §3 |
| F08 NetworkPolicy cannot do hostnames | accepted | ADR-026 amends ADR-008 mechanism |
| F09 ownership unenforced | accepted, blocked on remote | PR template reworded; CODEOWNERS stays placeholder until a remote exists |
| F10 secret-scan whole-line exemption | accepted, demonstrated | R.8 scanner fix + tests |
| F11 frozen sync ≠ lock check | accepted, demonstrated | R.8 `lock-check`, pinned build backend, pinned bootstrap |
| F12 evidence trail absent | accepted, open | roadmap Phase 4 task; user to supply or regenerate |
| F13 ČEPS labelling / completeness | accepted in part | roadmap Phase 4 verification task; contract keeps [UNVERIFIED] |
| F14 active docs disagree | accepted | R.9 reconciliation |

## Ordered tasks

| # | Task | Acceptance check | Commit |
|---|---|---|---|
| R.1 | `docs/reviews/2026-09-19-codex-review-response.md`: per-finding verdict, reasoning, action | file lists all 14 findings | `docs(review): response to Codex pre-coding review` |
| R.2 | ADR-022 source admission vs adapter addition (F04) | ADR accepted; Phase 7 protocol and 02 §5 criterion 4 pointer updated | `docs(adr): ADR-022 admission boundary` |
| R.3 | ADR-023 derivation identity and current-view selection (F05) | ADR accepted; ADR-018 carries "amended by"; roadmap Phase 1/2 field names updated | `docs(adr): ADR-023 derivation identity` |
| R.4 | ADR-024 capture durability, orphan reconciliation, backfill vs replay, lease fencing (F06) | ADR accepted; ADR-003 rev. carries "amended by"; roadmap Phase 2 ledger deliverable updated | `docs(adr): ADR-024 capture recovery invariants` |
| R.5 | ADR-025 upgrade verification hooks and install ordering (F07) | ADR accepted; ADR-016/ADR-021 carry "amended by"; roadmap Phase 5 wording updated | `docs(adr): ADR-025 upgrade hooks` |
| R.6 | ADR-026 egress boundary (F08) | ADR accepted; 02 ADR-008 pointer; roadmap Phase 5 wording updated | `docs(adr): ADR-026 egress boundary` |
| R.7 | ADR-027 target capability boundary (F03) | ADR accepted; ADR-014 carries "amended by" | `docs(adr): ADR-027 target capability boundary` |
| R.8 | Gate fixes: `testpaths` incl. `targets`; `tests/conftest.py` socket block; banned-api extension; `scripts/check_target_surface.py`; `scripts/secret_scan.py` narrowed exemption; `make lock-check`; pinned `hatchling`, uv installer, checkout SHA; pre-commit runs `check` + allowlist; tests for scanner, allowlist, surface check | `make check` green; `tests/harness/` negative tests prove each gate rejects its probe | one commit per gate |
| R.9 | Doc reconciliation (F14, F13, F12, F09): roadmap field names, example wording, Phase 4/5/7 tasks; 02 D-4 and ADR-008 notes; 00 purpose/A-3/A-5/A-13 notes; ADR-015 context; branch-protection wording; PR template wording | grep for `observed_at`, `CronWorkflow` outside superseded blocks returns nothing | `docs: reconcile active instructions with ADR-022..027` |
| R.10 | `docs/progress.md` entry; roadmap notes; memory | `make check` green | `docs(progress): review 1 closed` |

## Verification before each commit

`make check` (now = `lint` + `lock-check` + `type` + `test`), plus `make deps-allowlist secret-scan`.

## Stop conditions

- A finding needs a new runtime dependency → defer to the phase that uses it, note in the response.
- A finding needs the Git remote or a real GitHub handle (F09) → record as blocked on the user.
