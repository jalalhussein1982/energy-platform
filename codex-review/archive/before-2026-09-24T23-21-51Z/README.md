# Review verdict

Reviewed on **19 September 2026**, against the original assignment supplied in this conversation. Snapshot: `7d872eaa6e3b1f891bf199b803ae310b1ac6fa99`, branch `main`, **41 tracked files**. All existing tracked files were preserved. This directory contains review material only; no suggested change was implemented, committed, deployed, or submitted to anyone.

**Verdict: a promising design and repository bootstrap, but not a completed answer to the assignment.** The README accurately says Phase 0 and “No platform code yet.” If this is a design checkpoint, continue after resolving the contract contradictions below. If submitted as the finished take-home, I would mark the functional and reproducibility requirements as unmet.

The strongest evidence is the source-specific data design and the decision to give agents and humans one constrained contribution path. The weakest evidence is executable enforcement: the present gates do not establish that a junior or an agent can safely add even one target. There is no running ingestion path, deployment, IaC profile, or HA demonstration to evaluate.

| Evaluation order from the brief | Design assessment | What the supplied repository proves today |
|---|---|---|
| 1. Agentic engineering | Good separation of responsibilities and explicit authority; several contradictory instructions | Basic lint/type/import checks exist. No scaffold, manifest validator, negative harness, sandbox, protected remote, or blind addition test |
| 2. Data engineering | Strong attention to provenance, UTC/DST, decimals and source revisions; replay and recovery contracts need correction | Empty library and one version assertion; no capture, parser, database, migration, replay, or real target |
| 3. DevOps | Sensible portability and recovery intentions; excessive breadth before an executable slice | CI skeleton only. Reproduction commands are explicit failing stubs; deployment checks skip because inputs do not exist |
| 4. Energy domain | The most developed part; appropriately bounded Czech intraday monitoring scope | Detailed contracts and selected official-source corroboration, but missing original research evidence and no implemented domain tests |

This is an assessment of the delivered artifacts, not a judgment that the candidate cannot build the proposed system. Planned Phase 1–8 work is not being misreported as a regression in Phase 0.

The highest-value findings are:

- **F02–F03:** In an isolated copy, the check suite stayed green with direct target HTTP code and a deliberately failing target test. The test was not collected.
- **F04:** Adding an unseen source requires central admission/contract work, but the blind test forbids all changes outside the target directory and treats architectural guidance as failure.
- **F05:** The version/upsert key excludes parser or derivation identity, while replay is required to append corrected results from the same raw payload.
- **F06:** The design does not close the raw-write/ledger crash window or distinguish a missing capture from data that can actually be replayed.
- **F07–F08:** The Helm rollback and domain-based Kubernetes egress promises need different mechanisms from the ones currently specified.

Read the full material in this order:

1. [codex-review/01-assignment-assessment.md](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/01-assignment-assessment.md>) — what the original task requires, strengths, and readiness.
2. [codex-review/02-findings.md](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/02-findings.md>) — 14 prioritized findings with evidence and acceptance checks.
3. [codex-review/03-file-by-file.md](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/03-file-by-file.md>) — disposition of every tracked file.
4. [codex-review/04-validation.md](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/04-validation.md>) — commands, results, negative probes, and verification limits.
5. [codex-review/05-recommendations.md](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/05-recommendations.md>) — proposed sequence and demonstrations needed for submission.
6. [codex-review/06-primary-source-checks.md](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/06-primary-source-checks.md>) — external technical checks and remaining domain uncertainty.

**Verification qualification:** lint, formatting, import rules, mypy and the existing test passed using a copied installed environment, with dependency synchronization explicitly skipped. The unmodified `make check` path could not complete an offline isolated bootstrap because `hatchling` was not cached. No clean-machine installation, cluster deployment, live SOAP ingestion, outage drill, or production acceptance is claimed.
