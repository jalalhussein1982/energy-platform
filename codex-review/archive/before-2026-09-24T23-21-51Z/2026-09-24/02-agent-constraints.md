# Agentic engineering and extension review

Reviewed 2026-09-24 at `1701ac77175113d744abaad0514489711ed2b1d4`. Read-only review; persistent additions from this audit are this report and its evidence script/output. Probes created targets and Bronze fixtures in temporary directories and made no network requests, source edits, commits, or remote changes.

## Verdict against the brief

The extension architecture substantially meets the goal for **already admitted sources that fit the existing generic parsers**. It offers a narrow declarative surface, source admission instead of invented semantics, actionable validation, immutable Bronze fixtures, independently specified golden values, explicit PR scope, and many negative tests. This is a working harness, not merely a set of instructions. The evidence is strongest for developer-mode CLI contributions with a human reviewing fixture-derived goldens.

The remaining weaknesses are concentrated at the edges of that path: triage misses real changes in two supported SOAP shapes; the primary documented bundle workflow conflicts with its clean-checkout requirement; the bundle's green verdict omits the target's Python tests; and the shell-free MCP mode cannot deliver the Route B artifact it asks an agent to produce. Custom parsers and a real LLM client are explicitly deferred, so easy extension to arbitrary new source shapes is **not** established.

## Findings

### AE-01 — P2: triage reports `no_drift` for changed supported source fields

**Trigger.** A ČEPS XML attribute is renamed, or an OTE required time field changes name.

**Verified behavior.** Starting from the committed, synthetic ordinary-day Bronze fixtures, changing only ČEPS `value1=` to `value1New=` and recalculating the fixture hash produced:

```text
sample.fields = []
sample.dropped_fields = 3
pipeline observations = 192
pipeline NULL values = 96
pipeline events = [partition_status, unknown_field]
triage status = no_drift
triage missing_sources = []
triage unknown_fields = []
```

The second probe renamed OTE `<Date>`/`</Date>` to `<DeliveryDate>`/`</DeliveryDate>`:

```text
sample.fields = []
pipeline observations = 0
pipeline events = []
triage status = no_drift
```

**Cause and evidence.** `energy_platform/triage/extract.py:29` requires a letter as the first character of a safe field name, excluding the platform's `@date`, `@value1`, and `@value2` convention. Those fields are the actual T3 mapping (`targets/ceps_load/manifest.yaml:54`, `:60-61`). For non-tabular sources, the inventory is built only from records the existing generic parser already recognizes (`extract.py:75-82`); the XML parser recognizes a record only when every old required field is present (`energy_platform/parse/generic.py:104-111`). A renamed required field therefore erases the whole inventory. `energy_platform/triage/pipeline.py:151-175` checks missing and unknown fields only when this inventory is nonempty; it does not use the production outcome's `unknown_field` events. `pipeline.py:448-449` then returns `no_drift`, which the CLI maps to exit 0 (`energy_platform/cli.py:777`).

**Impact.** An operator receives a false healthy diagnosis when triaging an actual schema change. The ČEPS example has lost one entire metric's values while retaining the expected row count. This is a detection defect before any LLM is called; replacing the deterministic backend with a real model would not fix it. The OTE probe establishes the shared pipeline's empty result, not a new end-to-end database commit test.

**Recommendation.** Inventory decoded XML/JSON fields independently of successful mapping; admit the platform's legitimate attribute naming convention; carry production drift events into the report. Distinguish an empty source response from a nonempty source document whose records no longer match the declared shape. Add negative tests for a ČEPS attribute rename and an OTE required-time-field rename.

### AE-02 — P2: the primary documented CLI bundle workflow requires an undocumented clean second checkout

**Trigger.** A junior follows `docs/08-adding-a-target.md` literally: scaffold and edit a target in the checkout, then follow its primary Route A command block.

**Evidence.** The scaffold creates files directly under `targets/<id>/` (`docs/08-adding-a-target.md:60-79`; implementation `energy_platform/harness/scaffold.py:267-285`). The primary publish block then runs `pr-bundle` and `scripts.apply_pr_bundle … --push`, without committing, stashing, removing the generated files, or selecting another checkout (`docs/08-adding-a-target.md:191-199`). The apply command defaults to the current directory (`scripts/apply_pr_bundle.py:65`) and refuses *any* nonempty `git status --porcelain` before branching (`scripts/apply_pr_bundle.py:40-46`). A newly created target is untracked and an edited existing target is modified, so both meet that refusal condition.

**Impact.** The documented first-choice route stops with `working tree is not clean; commit or stash first`. The subsequent plain-Git alternative is viable, but the commands presented as the literal golden path cannot finish in the checkout they just prepared. The recorded acceptance runs used branch/commit/push directly (`docs/09-acceptance-report.md:29`, `:56-61`, `:143-147`), so they do not establish the bundle command block's usability.

**Verification level.** Confirmed by the caller/callee control flow and the existing dirty-tree refusal test (`tests/harness/test_pr_bundle.py:115-131`); this audit did not create a Git repository or run any Git mutation to repeat that test.

**Recommendation.** Make plain Git the primary CLI route, or explicitly send the bundle to a separate clean checkout with `--repo` and explain how source and destination differ. Exercise the exact documentation command sequence in a disposable repository, including its untracked target files.

### AE-03 — P2: a failing target test can receive a green PR bundle

**Trigger.** A target has valid fixtures/goldens and surface, but a failing Python test in `tests/test_*.py`.

**Verified behavior.** A temporary target built with the repository's own `make_target` helper received this additional allowed file:

```python
def test_known_failure() -> None:
    assert False, "REVIEW_SENTINEL_FAILURE"
```

The shared runner correctly failed, but bundle preparation succeeded and included the failing file:

```text
run_target_tests.ok = false
run_target_tests.pytest_exit = 1
gate_report.ok = true
prepare_bundle created a bundle = true
tests/test_failure.py included in that bundle = true
```

**Cause and evidence.** `energy_platform/harness/pr.py:41-59` runs surface validation, manifest admission, and golden comparisons only. It never runs the target's Python tests. `prepare_bundle` relies on that result (`pr.py:86-90`) and writes a default body saying the gates were green (`pr.py:101-103`). This conflicts with the CLI's “all gates green” promise (`energy_platform/cli.py:724`), the guide (`docs/08-adding-a-target.md:196`), and C-51's red-target refusal statement (`docs/05-constraint-matrix.md:106`). The dedicated runner does include pytest (`energy_platform/harness/runner.py:47-54`).

**Impact.** A contributor can get an authoritative-looking green bundle after the target's actual test command has failed, and MCP does not require a successful earlier test call before `open_pr`. CI can still reject the PR; this finding does **not** establish that a failing target can merge or deploy. In the sandbox, pytest is deliberately omitted (`deployment/sandbox/README.md:16`), so a full test claim is especially misleading.

**Recommendation.** Either require the relevant target tests before granting the bundle a complete green verdict, or make the bundle explicitly a partial-check artifact that records tests/lint/type checks as unrun and requires CI. Do not label unavailable or omitted checks as completed.

### AE-04 — P2: constrained MCP mode cannot produce its required admission request

**Trigger.** A shell-free agent encounters an unadmitted source and `validate_target` returns `ADMISSION_REQUIRED`.

**Evidence.** The MCP response tells the agent to run `energyctl admission-request <id>` and open a PR containing only that document (`energy_platform/mcp/tools.py:353-357`). The initialization message also instructs it to file a request (`energy_platform/mcp/server.py:61-65`). However, the exact tool table has no admission operation (`energy_platform/mcp/tools.py:45-54`), writes cannot escape a target (`tools.py:299-310`), and `open_pr` is Route A only (`tools.py:419-442`; `energy_platform/harness/pr.py:82-85`). The sandbox deliberately exposes only MCP, with no shell or Git (`deployment/sandbox/README.md:3-17`, `:33-36`).

**Verified guard results in a temporary repository:**

```text
call("admission_request", ...) -> unknown tool
write_target_file(..., "../../docs/admissions/probe_target.md", ...)
  -> escapes targets/probe_target/
```

**Impact.** Correct refusal works, but the constrained agent cannot complete the prescribed Route B deliverable through its allowed interface. It must hand the task to an operator with more authority; that dependency is not explained in the MCP section of the contributor guide (`docs/08-adding-a-target.md:205-225`). Developer-mode CLI Route B remains implemented, and the acceptance report provides evidence for it.

**Recommendation.** Add a narrowly scoped admission-request/outbox operation, with a corresponding ADR/tool-table update, or explicitly define Route B in constrained mode as a structured operator handoff and return that artifact instead of an unavailable command. Test Route B using only the sandbox's tool surface.

## Strengths verified in the current implementation

- **Admission is a meaningful boundary.** Route A references platform-owned dataset/metric/host registries; Route B is a valid outcome rather than pressure to fabricate semantics. The public guide explains both routes and excludes maintainer bookkeeping from target contributions (`docs/08-adding-a-target.md:7-27`, `:46-57`; ADR-022).
- **Small, positive target surface.** `energy_platform/harness/surface.py:26-70`, `:115-132`, `:158-211`, and `:278-344` define the file/import surface, reject common normalization and escape constructs, verify Bronze fixture hashes, and require checked golden files. This is materially stronger than the previous bootstrap's small import ban. It is still correctly described as a guardrail rather than an arbitrary-Python sandbox (ADR-027 §5).
- **Target tests and independent golden execution are collected.** `pyproject.toml:160-165` includes both `tests` and `targets`; `conftest.py:29-34` rejects incomplete targets; `energy_platform/harness/goldens.py:163-169` discovers every declared golden, independently of what a target's own test chooses to assert. This closes the historical omission of target tests from default collection.
- **No routine live source calls in the unit suite.** The default Make test selects `not live` (`Makefile:58-62`), with a Python socket guard on ordinary test execution (`conftest.py:46-54`). This is a guardrail, not an OS-level proof against arbitrary adversarial test code or all import-time/native-library activity.
- **Triage has a defensible output boundary.** The sample is limited to 3 records, 64 fields, 64 characters per value, and 4,000 serialized characters (`energy_platform/triage/extract.py:25-28`, `:80-89`). Model replies have a closed four-operation schema and bounded operation count (`pipeline.py:68-83`, `:210-234`), a semantic model-diff guard (`:419-427`), and produce only an outbox proposal (`:473-501`). Host/unit/sign/cadence changes cannot be expressed as repair operations. The capture/process import graph excludes triage (`pyproject.toml:143-155`).
- **Read/modify/propose are distinct from deploy.** MCP requires explicit live-fixture enablement (`energy_platform/mcp/tools.py:381-389`), confines direct file writes, and prepares an outbox bundle instead of pushing. PR scope classification rejects mixed platform/target changes and multiple targets (`energy_platform/harness/pr_surface.py:64-89`). Production authority in ordinary developer sessions remains procedural, accurately disclosed in `docs/threat-model.md:92-94`.

## Explicit scope limits and evidence limits

1. **Custom parsers are accepted but not executed.** The README explicitly lists the loader as deferred G13 (`README.md:138`; `docs/05-constraint-matrix.md:163`). A temporary target containing a syntactically valid parser whose `parse()` raises `CUSTOM_PARSER_WAS_CALLED` passed surface, goldens, and pytest; its parser reference remained `generic:soap@0.0.1`. The runtime always uses `generic_parser` (`energy_platform/runtime/process.py:151-154`) and generic lineage (`energy_platform/parse/generic.py:63-65`). This is an acknowledged capability limit, **not an undisclosed defect in the seven committed generic targets**. However, scaffolding still offers `parser.py`, and accepted ADR-017:18 and `docs/04-contracts.md:165-166` describe its registration convention. Until execution is supported, validation should fail clearly on a supplied custom parser or the scaffold should remove that option. A new source shape outside the generic parser's coverage needs a platform decision, even when its dataset and host are admitted.
2. **The LLM backend is a deterministic stub.** This is expressly disclosed in `README.md:137` and implemented by `energy_platform/triage/llm.py:43-79`. Injection tests establish the output guard's behavior against scripted hostile answers; they are not evidence of real-model repair quality. An absent model does not block ingestion, which is a good design decision.
3. **Acceptance evidence supports a narrower extension claim.** The report records Route A, Route B, CLI-only, and a later empty-profile run (`docs/09-acceptance-report.md:14-19`). The strictly blind run had a sibling version-1 target and changed a settlement version/month offset (`:149-175`). That is useful evidence for a familiar source family; it does not exercise a brand-new source shape, a custom parser, the primary bundle-apply command sequence, or a shell-free Route B session. This audit did not re-read external session transcripts or refresh GitHub PR/branch protection state.
4. **Sandbox verification remains mostly static.** Its tests inspect the Dockerfile and the documentation admits that CI does not probe a built image (`docs/threat-model.md:94`). No container build/run, live endpoint, remote infrastructure, or credentialed system was inspected by this audit.

## Local verification record

The following focused regression command ran against the current checkout using the existing environment, with bytecode and pytest caches disabled and all test output under `/tmp`:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTEST_ADDOPTS='-p no:cacheprovider' \
HYPOTHESIS_STORAGE_DIRECTORY=/tmp/ep-agent-review-hypothesis \
.venv/bin/python -m pytest \
  tests/triage \
  tests/harness/test_target_surface.py \
  tests/harness/test_mcp.py \
  tests/contracts/test_manifest_negative.py \
  -m 'not live' --basetemp=/tmp/ep-agent-review-pytest
```

Result: **196 passed in 1.77s**. The triage false-negative and green-bundle probes above passed through public library APIs despite that green focused suite. They are additional negative scenarios absent from the current tests, not failures manufactured by editing the checkout.

Probe method: `tempfile.TemporaryDirectory`; `tests.harness.targets_builder.make_target` for the target/bundle cases; `load_fixture` plus an updated SHA-256/size/raw reference and `write_fixture` for the two changed payloads; `check_target`, `run_target_tests`, `prepare_bundle`, `extract`, `run_pipeline`, and `triage` for the actual decisions. Temporary paths were removed automatically. No gates were weakened and no production fix was implemented.

The rerunnable script [evidence/agent-constraint-probes.py.txt](evidence/agent-constraint-probes.py.txt) reproduces AE-01, AE-03, and AE-04; captured output is [evidence/agent-constraint-probes.json](evidence/agent-constraint-probes.json). Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  codex-review/2026-09-24/evidence/agent-constraint-probes.py.txt
```

**Exit 0 means all reported defects were reproduced**, not that the application passed. The script records source hashes, blocks Python socket entry points, makes no Git calls, and removes temporary targets and bundles automatically. Its saved run reproduced all three findings with zero attempted socket calls. The `.py.txt` extension keeps report-only evidence out of repository-wide Python lint discovery.
