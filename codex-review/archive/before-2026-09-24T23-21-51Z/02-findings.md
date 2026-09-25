# Findings

Priorities are relative to this assignment: **P1** blocks a core claim or should be resolved before its dependent implementation; **P2** is a material correctness, evidence or maintainability issue. There are **9 P1 and 5 P2 findings**. No P0 production incident is alleged. “Demonstrated” means exercised in an isolated copy; “design contradiction” and “unimplemented requirement” are deliberately separate categories. All recommendations below are proposals only.

## F01 — P1 — The requested system and reproduction path are absent

**Type:** unimplemented requirement, already acknowledged by the repository.

**Evidence:** [README.md:7](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/README.md:7>), [energy_platform/__init__.py:1](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/energy_platform/__init__.py:1>), [energy_platform/contracts/__init__.py:1](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/energy_platform/contracts/__init__.py:1>), [tests/test_placeholder.py:1](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/tests/test_placeholder.py:1>), [Makefile:78](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/Makefile:78>). The 41-file inventory contains no deployment tree or implemented target. `make demo`, `local-up`, `smoke-test` and `new-target` all returned Make exit code 2 after an explicit recipe failure. Helm/Terraform checks returned 0 by skipping absent inputs.

**Impact:** an evaluator cannot run the requested data system, exercise HA, or add a scraper through the proposed interface. A green bootstrap is not a system-level acceptance result.

**Recommendation / acceptance:** retain the truthful Phase 0 label until clean-clone capture-to-query, deployment and contributor demonstrations exist. Require a separate submission gate that fails when required artifacts or demonstrations are missing. Do not count bootstrap skip results as deployment passes.

## F02 — P1 — Ordinary test collection excludes the proposed target tests

**Type:** demonstrated configuration gap; automatic target discovery is planned for Phase 3.

**Evidence:** [pyproject.toml:111](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/pyproject.toml:111>) sets `testpaths = ["tests"]`; [Makefile:39](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/Makefile:39>) invokes pytest without a target path. The mandated target layout puts tests under `targets/<id>/tests/` ([docs/02-architecture-decisions.md:263](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/02-architecture-decisions.md:263>)).

**Reproduction:** added a test that unconditionally raises `AssertionError` under `targets/review_probe/tests/` in the isolated copy. The component-equivalent `make check` still passed with one test. Explicitly selecting the target test failed. See [codex-review/evidence/adversarial-probes.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/adversarial-probes.json>).

**Impact:** a contributor can currently receive green checks despite broken target goldens, or provide no manifest/fixtures at all. This matters before any target is admitted, even though no target exists today.

**Recommendation / acceptance:** implement the promised target collector and validate required target artifacts before collection. A new target test must execute by default; a missing fixture/golden and a failing golden must each fail the normal required CI path. Include a passing target control to prove the collector does not merely reject everything.

## F03 — P1 — The current egress lint policy does not enforce its stated boundary

**Type:** demonstrated gate bypass.

**Evidence:** [pyproject.toml:60](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/pyproject.toml:60>) bans five HTTP client imports but does not ban `http.client`; [pyproject.toml:87](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/pyproject.toml:87>) forbids selected internal imports rather than positively limiting target capabilities. [AGENTS.md:35](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/AGENTS.md:35>) requires all outbound HTTP to go through the platform fetch package.

**Reproduction:** a target parser defining a typed function using `http.client.HTTPSConnection`, `request` and `getresponse` passed Ruff, mypy and import-linter. No HTTP function was executed and no network request was made. The same isolated check run as F02 stayed green.

**Impact:** a junior can accidentally bypass shared timeout, retry, politeness, proxy, host and audit logic using an ordinary standard-library API. Banning a few imports cannot be treated as an isolation mechanism for arbitrary Python.

**Recommendation / acceptance:** define the allowed parser capabilities, reject known direct egress paths and control suppressions, and enforce network isolation for parser/test execution. Negative controls should cover standard-library HTTP, sockets, dynamic imports and subprocess paths without contacting the internet. Keep static lint described as a guardrail rather than a complete sandbox.

## F04 — P1 — The unseen-source acceptance test conflicts with admission and contract rules

**Type:** design contradiction.

**Evidence:** [docs/01-data-scope.md:185](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:185>) disallows new dimensions/units/metrics outside the registry; [docs/01-data-scope.md:320](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:320>) requires a central admission row for every new target. [AGENTS.md:31](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/AGENTS.md:31>) prohibits editing the frozen scope docs inside a task. Yet [docs/03-roadmap.md:188](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/03-roadmap.md:188>) gives a fresh contributor only an unseen URL and treats core changes or architectural guidance as a harness defect; the target PR may touch only `targets/<id>/`.

**Failure example:** an unseen Open-Meteo dataset, explicitly suggested by Phase 7, needs metric semantics and admission outside its target directory. Following policy means stopping for approval; following the blind-test success condition means bypassing policy. E1 is useful but already contracted and admitted, so it does not resolve this conflict.

**Recommendation / acceptance:** distinguish adding an adapter for a pre-approved contract from admitting a new source/dataset/metric. Either pre-admit the held-out contract or define a declarative, separately reviewed admission workflow. A good harness should guide a legitimate escalation; escalation must not automatically count as failure. Test both routes and define their expected touch surfaces.

## F05 — P1 — The frozen version key makes parser-repair replay a no-op

**Type:** design contradiction, not an executed database defect.

**Evidence:** [docs/adr/ADR-018-canonical-schema-details.md:16](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/adr/ADR-018-canonical-schema-details.md:16>) makes version identity and the upsert key `(business identity, source_version, payload_sha256)` and says identical payload reruns are no-ops. [docs/01-data-scope.md:279](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:279>) requires the same raw document, parsed with a new contract version, to produce distinguishable rows. [docs/adr/ADR-016-release-and-rollback.md:19](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/adr/ADR-016-release-and-rollback.md:19>) depends on replay to repair bad derived data. ADR-018 also equates `parser_version` with `contract_version`.

**Failure example:** parser A reads payload H and writes an incorrect sign. Parser B fixes the sign without changing business identity, source version or H. The specified conflict key is identical. A no-op preserves the wrong value; overwriting violates append-only history. A bug fix also need not change a semantic contract version.

**Recommendation / acceptance:** separate provider revision identity from derivation identity, including parser/mapping implementation provenance. Define which derivation becomes current, how ties are resolved and how superseded wrong rows remain auditable. Prove: exact retry adds nothing; same payload/new derivation appends corrected output; replaying older source data never supersedes newer data; T1/T2 ownership survives both operations. Resolve by ADR before creating migrations.

## F06 — P1 — Recovery does not connect orphaned Bronze, missing captures and replay

**Type:** missing architecture invariant.

**Evidence:** [docs/02-architecture-decisions.md:189](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/02-architecture-decisions.md:189>) orders raw persistence and acknowledgment before ledger registration; processing reads the ledger. [docs/02-architecture-decisions.md:244](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/02-architecture-decisions.md:244>) says replay never refetches, while the gap detector enqueues replays for missing intervals. [docs/adr/ADR-003-rev-orchestration-without-crds.md:18](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/adr/ADR-003-rev-orchestration-without-crds.md:18>) gives one run per target/scheduled time but does not define capture-versus-processing attempts or replay identity.

**Failure examples:** (1) a capture blob/log is durable, then PostgreSQL is down or the worker dies before inserting its ledger row; no specified reader discovers that capture. (2) the scheduler never captures a period, leaving nothing to replay. (3) an expired worker resumes after a new lease owner has claimed the same work; lease fields alone do not specify fencing at commit.

**Recommendation / acceptance:** specify a recoverable capture manifest or outbox/reconciliation boundary, immutable capture identity, processing attempts, atomic output/state commit, and lease fencing. Separate refetch/backfill for absent captures from reprocessing existing Bronze. Test crashes before and after each durable boundary, DB outage during capture, absent raw data, duplicate claims and a stale lease holder. Preserve original fetch metadata during repair. A missing historical payload may be unrecoverable; report that explicitly.

## F07 — P1 — A Helm test hook is not an automatic upgrade rollback check

**Type:** incorrect deployment mechanism in a locked decision.

**Evidence:** [docs/adr/ADR-016-release-and-rollback.md:17](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/adr/ADR-016-release-and-rollback.md:17>) promises automatic rollback using `helm upgrade --atomic --wait` plus a `helm test` hook. [docs/adr/ADR-021-bronze-tiering.md:21](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/adr/ADR-021-bronze-tiering.md:21>) similarly says a test-hook storage probe fails the deployment. The roadmap repeats both.

**Why:** a hook annotated `test` runs through `helm test`; it is not automatically a `post-upgrade` hook. A separate test command after a successful upgrade is outside that completed atomic upgrade. A CronJob can install successfully without its workload ever running. See [Helm 3 chart tests](https://docs.helm.sh/docs/v3/topics/chart_tests/) and [hook lifecycle](https://docs.helm.sh/docs/v3/topics/charts_hooks/).

**Recommendation / acceptance:** use an appropriate blocking install/upgrade hook, or an explicit deploy workflow that runs tests and rolls back on failure. Define first-install migration ordering too: a `pre-upgrade` hook does not bootstrap the database on installation. Inject a broken parser and a failing storage probe and show the prior release is restored, schema compatibility holds and raw captures remain recoverable. No Helm deployment was run during this review.

## F08 — P1 — Standard NetworkPolicy cannot implement a per-hostname egress promise

**Type:** incorrect portability/security assumption.

**Evidence:** [docs/02-architecture-decisions.md:321](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/02-architecture-decisions.md:321>) requires Kubernetes NetworkPolicy to allow only the manifest's declared hosts. [docs/03-roadmap.md:158](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/03-roadmap.md:158>) carries that into the tenant chart, whose core is supposed to need no extra cluster capability.

**Why:** the standard API selects pods, namespaces and IP blocks, not arbitrary DNS hostnames or HTTP redirects. Policy also needs an enforcing network plugin. An approved hostname can resolve to a private address, and a contributor-controlled allowlist is not independently approved policy. Application checks and an egress boundary have different jobs. See [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

**Recommendation / acceptance:** choose and document a tenant-compatible egress proxy, or explicitly require verified platform-provided FQDN enforcement. Specify scheme/port rules, private/metadata-address denial, DNS resolution handling and every redirect hop in the fetch layer. Keep necessary DNS/storage/database traffic explicit. Tests should demonstrate both a legitimate capture and blocked redirects/private destinations under the actual deployment CNI. No live SSRF test was performed.

## F09 — P1 — Human ownership and agent authority remain unenforced locally

**Type:** acknowledged operational delivery gap, with overstatement in the PR template.

**Evidence:** [CODEOWNERS:1](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/CODEOWNERS:1>) uses a placeholder everywhere. [docs/branch-protection.md:3](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/branch-protection.md:3>) says settings are to be applied once a remote exists; `git remote -v` is empty. [docs/progress.md:25](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/progress.md:25>) says the pre-commit hook is not installed. [.github/pull_request_template.md:10](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/.github/pull_request_template.md:10>) says CI enforces each constraint row, while the constraint matrix and most gates are future Phase 3 work.

**Impact:** ownership, a protected base branch and a target-only path boundary are not demonstrated. The version assertion, dependency checker and secret scanner do not enforce manifest validity, admission or target scope. An agent-written checklist is not evidence of authority separation.

**Recommendation / acceptance:** before claiming the harness is ready, configure real owners and protected checks with bypass restrictions, and test rejection on the Git host. Ensure critical validation logic and policy changes require trusted human review; a target PR must not redefine its own policy or manipulate the oracle. Show that an agent identity cannot merge, obtain deployment secrets, change gates, or broaden its write surface. This does not require giving the reviewer private credentials.

## F10 — P2 — Secret scanning exempts entire lines containing ordinary words

**Type:** demonstrated false negative.

**Evidence:** [scripts/secret_scan.py:29](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/scripts/secret_scan.py:29>) exempts any line matching `example`, `placeholder`, several markers or an environment-variable suffix; [scripts/secret_scan.py:56](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/scripts/secret_scan.py:56>) skips it before testing any credential pattern.

**Reproduction:** the same synthetic GitHub-token-shaped marker is detected alone but not with `# example`, or inside an `https://example.org/` URL. All markers were fake. See [codex-review/evidence/adversarial-probes.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/adversarial-probes.json>).

**Impact:** documentation, copied configuration or code can contain a real-looking credential and a harmless explanatory word and evade the gate. `fetch-depth: 0` in CI does not make this scanner inspect history; it only scans current files. Lockfiles and undecodable/binary files are also skipped.

**Recommendation / acceptance:** narrowly scope placeholder exclusions to the actual candidate value or a reviewed explicit exception. Add maintained scanner tests for comments, URLs, common provider formats and history policy. State exactly what is scanned. This finding does not claim any real secret was found or leaked.

## F11 — P2 — Frozen synchronization does not validate lockfile consistency

**Type:** demonstrated command semantics plus a reproducibility gap.

**Evidence:** [Makefile:24](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/Makefile:24>) uses `uv sync --frozen`; [.github/workflows/ci.yml:13](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/.github/workflows/ci.yml:13>) sets `UV_FROZEN=1`. The allowlist only checks names already present in the lock ([scripts/check_deps_allowlist.py:17](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/scripts/check_deps_allowlist.py:17>)). There is no separate up-to-date-lock check.

**Reproduction:** in the isolated copy, changed the dev requirement from `pytest>=8.3` to `pytest>=100` without updating the lock. `uv sync --frozen --offline --group dev --no-install-project` still succeeded with the installed pytest 9.1.1 environment. The project-install skip isolates synchronization semantics and is not claimed as a full build test. Astral explicitly documents that frozen mode omits the freshness check: [locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/).

**Recommendation / acceptance:** add a separate locked consistency check and demonstrate that a pyproject-only dependency edit fails. Keep offline runtime tests separate from dependency installation. Also account for build/bootstrap provenance: `hatchling` is unpinned and absent from the supplied lock/allowlist, the uv installer URL is mutable, and checkout uses a major-version tag. Lockfile package hashes alone do not pin every executable input. The offline bootstrap failure observed here is a review environment limitation, not proof that a normal online install fails.

## F12 — P2 — The source evidence trail is not included in the reviewed repository

**Type:** acknowledged evidence gap.

**Evidence:** [docs/01-data-scope.md:13](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:13>) relies on `message-board/evidence/SOURCES.md`, `SOURCES-round-2.md`, samples and hashes. None is in the 41 tracked files or initial visible file inventory. [docs/progress.md:11](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/progress.md:11>) already flags this exact issue.

**Impact:** an evaluator cannot reproduce or audit the cited S01–S17 reads, the DST workbook layouts, rolling-fill observations or the asserted ČEPS semantics from the supplied package. Narrative assertions that something was verified are weaker than the cited evidence itself.

**Recommendation / acceptance:** supply an appropriately redistributable evidence index with request shape, observation time, source/version, digest, bounded extracted facts and an explicit synthetic-fixture policy. Where raw source redistribution is unresolved, do not indiscriminately commit captures. Mark unavailable evidence as unavailable and provide lawful regeneration instructions. Selected OTE facts were corroborated from official sources in this review; that does not reconstruct the missing ledger or establish all claims.

## F13 — P2 — Energy completeness and timestamp confidence need more precise contracts

**Type:** domain ambiguity that should be settled before goldens become authoritative.

**Evidence:** [docs/01-data-scope.md:118](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:118>) asserts ČEPS QH/AVG timestamps mark interval starts while acknowledging the detailed interface document was not parsed. A live numeric sample and an offset do not alone prove interval labeling. [docs/01-data-scope.md:158](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:158>) requires owning-transport metrics for completeness, while [docs/01-data-scope.md:294](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:294>) allows NULL prices for both no trade and not-yet-published data. [docs/01-data-scope.md:173](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/01-data-scope.md:173>) associates network/HTTP failure with ingestion failure and implies HA replicas fix it.

**Impact:** an end-labeled load feed treated as start-labeled shifts data by 15 minutes. Treating every NULL as missing can keep a valid no-trade period permanently late; treating every returned row as complete can hide unpublished data. Source-side 5xx/timeouts and local failures can have the same HTTP symptoms; an unchanged payload can be valid after completion. Whole-file hashes measure byte change, not economic freshness.

**Recommendation / acceptance:** retain the ČEPS interval convention as unverified until backed by source documentation or an independent reference. Define row presence, publication state, no-trade/null reason, expected metrics and source finality separately. Add a complete day containing a legitimate null, a rolling partial day, an unchanged completed payload, a SOAP fault carried over HTTP success, and source-side versus local failures. State when cause is unknown. Preserve the original claim labels rather than manufacturing certainty; this review does not assert ČEPS is actually end-labeled.

## F14 — P2 — Active instructions still disagree after the reconciliation pass

**Type:** documentation defects with implementation consequences.

**Evidence and examples:**

| Active instruction | Conflict |
|---|---|
| [docs/03-roadmap.md:70](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/03-roadmap.md:70>) names `published_at` and `observed_at` | ADR-018 explicitly rejects `observed_at`; 01 requires `source_published_at`, `fetched_at`, `processed_at` |
| [docs/03-roadmap.md:73](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/03-roadmap.md:73>) asks for five examples but lists T1, T2, T3 plus HTML and two REST examples | Six target examples if all are distinct; T1 and T3 share SOAP. Progress line 9 instead describes three real plus two shape-only examples |
| [docs/02-architecture-decisions.md:452](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/02-architecture-decisions.md:452>) defaults the gap detector to `CronWorkflow` | Revised orchestration explicitly prohibits Argo and uses `CronJob` |
| [docs/00-assumptions.md:36](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/00-assumptions.md:36>) still derives cold-tier lifecycle behavior; line 38 says namespace-scoped token | Later ADR-021 uses a platform tiering job; ADR-015 says cluster-scoped Rancher token |
| [docs/branch-protection.md:21](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/branch-protection.md:21>) implies `make check` through pre-commit | Actual hooks run lint/type/secret scan, omit tests, and the hook is not installed |
| [docs/03-roadmap.md:54](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/docs/03-roadmap.md:54>) says the ADR-019 allowlist is seeded | Current allowlist has locked dev packages; runtime approvals are only comments, consistent with the Phase 0 plan but not this checkbox wording |

**Impact:** the next agent can faithfully follow one authoritative document and violate another. Freeze rules make this more consequential: ambiguity becomes repeated approval/ADR churn or silent invention.

**Recommendation / acceptance:** use the existing ADR process to identify the canonical contract and reconcile active instructions. Keep explicitly superseded historical prose recognizable as history. A consistency check should resolve every required read path or identify it as a future deliverable; agree an exact example list, field names and authority vocabulary before Phase 1.
