# Final review against the original assignment

**Verdict: a substantial working ingestion system and a credible agent-contribution demonstrator, but not yet an accepted high-availability data platform.** It delivers real observations, has reproducible checks and considerable operational engineering. Reproduced correction, replay, current-value and restore defects prevent an unqualified claim that its output remains correct through failures. The demonstrated infrastructure also has single points of failure.

Reviewed on **24 September 2026**, source commit **`1701ac77175113d744abaad0514489711ed2b1d4`**, branch `main`, **573 tracked files**. This review preserves the older Phase 0 report in the parent directory. Its obsolete “no platform code” assessment does not describe this implementation.

**No application, configuration, infrastructure, GitHub setting or live database content was changed.** Local checks ran in a temporary source copy or against disposable test state. Live database queries were aggregate SELECTs with `default_transaction_read_only=on` and `BEGIN READ ONLY`. Deliverables and reproducible counterexamples are confined to this review directory.

## Does it meet the brief?

| Original requirement | Verdict | Evidence and qualification |
|---|---|---|
| Lead and constrain junior engineers / LLM agents | **Substantially delivered for admitted, supported source shapes** | Positive target surface, registries, CLI/MCP, negative tests, source-admission route, protected-main checks and real target-only PRs. Four remaining tooling defects are in AE-01–04. Arbitrary source shapes/custom parser execution and shell-free Route B completion are not established. |
| Scrape and process public intraday energy data | **Delivered, with correctness blockers** | Read-only live queries found **108,872 historical observation rows** across five dataset/transport/version groups at the sampled instant. Seven targets are configured; five have run/data evidence. The monthly and final targets had no ledger runs or v1/v2 observations yet. Corrections and current-source selection can still return wrong results (DC-01–06). |
| High availability and recovery | **Partially delivered; acceptance not met** | Raw-first capture, run ledger, fences, retry, backfill, independent storage, WAL/base backups and a successful B-only drill exist. Recovery counterexamples remain; the demo has one k3s server and one PostgreSQL instance pinned to it. Hourly replication does not meet the stated cross-provider loss bounds. |
| Reproducible testing, deployment and IaC | **Strong implementation and current validation; full fresh infrastructure reproduction not rerun** | Full local checks, DB tests, offline demo, fresh virtualenv installation, Helm renders, both Terraform roots and six mocked plan tests passed. Latest CI/deploy are green. No fresh cluster was created under this read-only review. Alternate CNPG/external recovery wiring is incomplete. |
| Choose suitable data and understand its semantics | **Strong fixture-level evidence; live-output semantics need repair** | Independent code, importing no platform modules, checked 42 positive fixtures, 215 expected values/UTC instants and their expected row counts. DST, native hourly intervals, negative/zero/null values and settlement versions are represented. SOAP ownership is declared but not honored by the current view; freshness is not scoped to a target's version. |

The absence of a web UI, consumer API, ENTSO-E adapter or live LLM repair client is **not itself a failure of the original brief**. SQL is a reasonable output interface, ENTSO-E is optional, and keeping LLMs outside the ingestion path is sound. The main issue is dependable behavior of the system that was built.

## What is confirmed to work

- `make check`: **887 passed, 25 skipped, 8 deselected**, plus lint, format, lock, strict typing and harness gates.
- `make db-test`: **26 passed** against disposable PostgreSQL 18.4, including migration round trips.
- `make demo`, dependency allowlist, secret scan and Helm checks for three profiles: **passed**.
- Fresh empty temporary virtualenv installation from `uv.lock`: **passed**. This was on the existing laptop, not a clean OS.
- Terraform formatting, backend-disabled initialization, validation and mocked tests: **3/3 hcloud and 3/3 OpenStack passed**. No real cloud plan or apply.
- Bounded live source smoke: **7/7 passed**. These are document/shape checks, not price correctness, freshness or nonempty-output guarantees.
- GitHub: [HEAD CI passed all 12 jobs](https://github.com/jalalhussein1982/energy-platform/actions/runs/36004869532); [latest applicable deployment succeeded](https://github.com/jalalhussein1982/energy-platform/actions/runs/36003743511). HEAD is a README-only follow-up to the deployed commit.
- Hetzner demo: both nodes Ready, recent capture/process/replication jobs completed, PostgreSQL and exporter running. Existing successful restore-drill logs were inspected; no new live drill was started.

These are useful achievements. The defects below are additional cases that remain reproducible despite those green checks.

There are **17 findings: 8 P1 and 9 P2**. The reports define triggers, evidence, impact and proposed acceptance checks. The disclosed single-server HA limit is assessed separately from this defect count.

## Findings that most affect acceptance

1. **Corrections can remain unprocessed after database recovery, or be skipped when an older worker commits** (DC-01, DC-02). Bronze contains the newer payload, but the ledger finishes with the old data and no pending work.
2. **The current view can select the wrong source or a superseded value** (DC-03, DC-04). XLSX displaces the declared SOAP system of record. A provider sequence A → B → A leaves B current because the second occurrence of A is deduplicated away.
3. **Recovery is not yet semantically safe** (DC-05–07). An expired replay can remain stuck; concurrent captures can share one log identity; a successful rebuild can restore previously removed invalid data. The last case is acknowledged in the runbook and reproduced by the review.
4. **Freshness can report another target's data as this target's success** (DC-08). A monthly target with no runs can be labeled complete using daily version-0 rows. The live snapshot also showed shared newest-delivery timestamps for monthly targets with no captures.
5. **The deployed topology and independent-copy schedule do not establish HA** (DEP-01 plus the topology acceptance gap). A second worker does not provide a second control plane or database. Store B is updated hourly, not within the 15-minute target.
6. **Several advertised optional paths and controls are incomplete** (DEP-02–05, AE-01–04): alternate database recovery, effective FQDN restrictions, fail-closed external database destinations, policy-readiness detection, triage and parts of the contribution workflow.

The core correction/current/replay/freshness counterexamples were reproduced both in memory and against **real disposable PostgreSQL**, not inferred from documentation alone. Concurrent object-store behavior and CNI timing were not exercised against live services; those findings state their evidence limits.

## Read the report

1. [Assignment assessment and coherence](01-assignment-and-coherence.md) — how the design and delivered behavior compare with the original task.
2. [Agent constraints](02-agent-constraints.md) — AE-01–04, strengths and extension limits.
3. [Data correctness](03-data-correctness.md) — DC-01–08 with triggers, code references and counterexamples.
4. [Deployment and HA](04-deployment-and-ha.md) — DEP-01–05, topology, DR and observability.
5. [Verification and live evidence](05-verification-and-live-evidence.md) — commands, current remote evidence and verification boundaries.
6. [Proposed remediation and acceptance](06-proposed-remediation-and-acceptance.md) — the order of work to discuss, with measurable exit criteria. **No fixes implemented.**

**Submission decision:** I would accept this as evidence of substantial engineering ability and a functioning demonstration. I would request changes before accepting the original assignment as fully complete, and would not rely on its HA/correction guarantees until the blocking cases pass. The next step is agreement on the remediation scope, starting with data correctness and recovery.
