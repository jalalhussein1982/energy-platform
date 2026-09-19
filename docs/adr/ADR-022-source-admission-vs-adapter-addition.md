# ADR-022 — Source admission versus adapter addition

| | |
|---|---|
| Status | ACCEPTED |
| Date | 2026-09-19 |
| Resolves | Codex review F04; amends `02` §5 criterion 4 and `03` Phase 7 |
| Supersedes | — |

## Context

`01-data-scope.md` §6 says a target registers a contract and cannot invent dimensions, units or
metric names; §10 says no target is added without a human-reviewed admission row. `03` Phase 7
handed a fresh contributor an unseen URL, forbade edits outside `targets/<id>/`, and counted any
need for a core change or architectural guidance as a harness defect. Both cannot hold for a
source whose `dataset_id` does not exist yet: the honest contributor must stop and ask, and the
protocol scores that as failure. The review (F04) is right that this pushes an agent toward
inventing units or widening policy to "pass".

## Decision

1. **Two routes, two touch surfaces.**

   | Route | Precondition | Touches | Reviewer |
   |---|---|---|---|
   | **A — adapter addition** | `dataset_id` exists in the platform registry with its identity key and metric set; every host in `allowed_hosts` exists in the platform host registry (ADR-026); the manifest's `contract.metrics` ⊆ the registered set | `targets/<id>/` only | CI + one human approval of goldens |
   | **B — source admission** | anything else: new `dataset_id`, metric, unit, sign convention, null meaning, or host | platform PR: registry entry (`energy_platform/contracts/registry.py`, Phase 1), host registry entry, a new row in `01` §10, and where needed an ADR | CODEOWNERS (human) |

   Route A is the junior/agent golden path and is what the harness must make safe. Route B is a
   maintainer decision that no gate can automate, because it is a licensing and semantics
   judgement.

2. **Correct agent behaviour on an unadmitted source is to stop with an admission request.**
   `energyctl validate` (Phase 3) reports `ADMISSION_REQUIRED` and lists exactly what is missing.
   The agent writes `docs/admissions/<id>.md` from a template (source, endpoint, license/terms
   URL, proposed `dataset_id`, identity key, metrics with unit/sign/null meaning, hosts, sample
   shape) and opens a PR containing only that file. Inventing a unit, editing the registry from a
   target PR, or marking a metric "unknown" to pass validation is the failure mode; the gates in
   Phase 3 reject each (`docs/05-constraint-matrix.md` rows: "unregistered dataset_id",
   "unregistered metric", "host not in registry", "registry edit inside a target PR").

3. **Phase 7 runs both routes and scores escalation as a pass.**
   - Run 1 (Route A): a held-out source that was **pre-admitted** in Phase 6 by the maintainer
     through Route B (contract + §10 row, no adapter). Expected: a PR touching only
     `targets/<id>/`, green CI, goldens checked by hand.
   - Run 2 (Route B trigger): an unadmitted source. Expected: an admission request and no other
     change. Any registry edit, fabricated unit or widened allowlist is a defect of the run, not of
     the harness; a run that needed core edits to *succeed on Route A* is a harness defect.
   - The held-out source for run 1 is chosen in Phase 6 from `01` §4 (candidate list), admitted
     by the maintainer, and not built before Phase 7.

4. `02` §5 criterion 4 reads: "a fresh agent, given only the README and the URL of a
   **pre-admitted** unseen source, opens a PR that passes CI and touches nothing outside
   `targets/<id>/`; given an **unadmitted** source, it produces an admission request and nothing
   else."

## Rationale

The brief grades how contributors are constrained. A harness that makes an agent choose between
policy and "success" measures the wrong thing. Splitting the routes makes the automated path
genuinely target-only (Route A) and keeps the judgement call where a human is (Route B), and the
blind test then measures both the golden path and the escalation discipline.

## Rejected

- Pre-admitting every plausible source up front (the registry would become a wish list;
  admission is a licensing decision per source).
- Letting a target PR add registry entries "subject to review" (the reviewer would be reviewing
  semantics inside an adapter diff; CODEOWNERS on the registry is the stronger control).
- Keeping Phase 7 as written and treating escalation as failure (rewards fabrication).

## Consequences

- Phase 1: the `contract` block of the manifest references a registered `dataset_id`; the
  registry module is platform code under CODEOWNERS.
- Phase 3: `ADMISSION_REQUIRED` validation result; `docs/admissions/` template; four constraint
  rows listed above.
- Phase 6: maintainer admits one held-out candidate via Route B (this is also the Route B demo).
- Phase 7: two runs, both recorded in `docs/08-acceptance-report.md`.
- Devil's advocate: Route B is a human bottleneck. Accepted — it is one row and one registry
  entry per source, and it is the point at which licence and redistribution are checked.

## Verification refs

none — design decision.
