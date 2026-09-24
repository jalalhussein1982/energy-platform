# Documentation index

Start with the repository [`README.md`](../README.md). The numbered documents are the design and
its evidence, in the order they were written; `00`–`02` are frozen and change only through an ADR.

| Document | What it is |
|---|---|
| [`00-assumptions.md`](00-assumptions.md) | The assumptions register (reference environment, scenarios A/B/C, cost if false) and the verification log V-1 … V-14 with raw evidence |
| [`01-data-scope.md`](01-data-scope.md) | What is collected and why: source contracts (T1, T2, T3, E1), candidates, freshness contract, DST and decimal rules, the source admission register (§10) |
| [`02-architecture-decisions.md`](02-architecture-decisions.md) | ADR-000 … ADR-013, the open decisions D-1 … D-13 and their resolution |
| [`adr/`](adr/README.md) | The ADR log and ADR-014 … ADR-037 |
| [`03-roadmap.md`](03-roadmap.md) | Phases 0 … 8 with their gates, checkboxes and the session protocol |
| [`04-contracts.md`](04-contracts.md) | The canonical observation, the manifest, the dataset registry, goldens |
| [`05-constraint-matrix.md`](05-constraint-matrix.md) | 61 failure modes, each with its gate and a negative test; the CI gate inventory |
| [`06-source-verification.md`](06-source-verification.md) | Bounded live reads of every source (hashes, shapes, terms, quirks), incl. the held-out admission (§9) |
| [`07-operations.md`](07-operations.md) | The runbook: image, local profile, Terraform, the live demo (§4.1), backups and restore, rollback drill, observability, the clean-clone gate (§8) |
| [`08-adding-a-target.md`](08-adding-a-target.md) | **The contributor's page**: adding a data source, both routes |
| [`09-acceptance-report.md`](09-acceptance-report.md) | Phase 7: three blind runs, findings, verdict |
| [`architecture.md`](architecture.md) | Diagrams: data path, contributor and triage path, demo deployment |
| [`threat-model.md`](threat-model.md) | 15 threats with mechanism, gate and residual risk (ADR-008) |
| [`branch-protection.md`](branch-protection.md) | The `main` protection settings as enforced on GitHub |
| [`ci-porting.md`](ci-porting.md) | Moving the CI wrappers to GitLab |
| [`admissions/`](admissions/) | Route B records: the template, the admitted held-out source, the refused EPEX demo |
| [`evidence/`](evidence/README.md) | Index of the source reads behind `01` §3 (payloads stay outside the repository) |
| [`plans/`](plans/) | One plan per phase, with the decisions taken while executing it |
| [`progress.md`](progress.md) | The development log from Phase 5 on; earlier entries in [`archive/`](archive/) |
| [`reviews/`](reviews/) | Responses to the two external reviews: pre-coding (2026-09-19) and final against the brief (2026-09-24, 17 findings, Phase 10) |
| [`overview/`](overview/) | A one-page illustrated explainer (HTML/PDF) |
