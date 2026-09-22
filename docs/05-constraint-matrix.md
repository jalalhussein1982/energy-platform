# 05 — Constraint matrix: failure mode → gate → test that proves the gate

| | |
|---|---|
| Status | Active, v1.0 (2026-09-20). Implements `docs/03-roadmap.md` Phase 3. Every row has a **mechanical** gate (a Make target CI calls, a library check the CLI and the MCP server share, or a runtime refusal) and a **negative test** that plants the failure and asserts the mapped gate rejects it. A row without both is a defect of this document. |
| Sources | `docs/02-architecture-decisions.md` ADR-005 (extension contract), ADR-006 (authority), ADR-007 (MCP), ADR-008 (threat model); `docs/adr/` ADR-014, ADR-016, ADR-017, ADR-020, ADR-022, ADR-026, ADR-027; `docs/00-assumptions.md` A-7, A-8; `docs/04-contracts.md` §3.7. |
| Predecessor | `docs/04-contracts.md`. Successor: Phase 4 (targets built through these gates), Phase 7 (blind runs measured against this table). |
| Rule | **Never weaken a gate to make a negative test easier** (03 Phase 3 "Do not"). A gate that cannot be exercised offline is not a gate; it is a hope. |

## 0. How to read this table

- **Gate** names the mechanism and the Make target that runs it in CI (ADR-015: one job per target,
  no logic in the workflow). `lint` = `make lint` (ruff, ruff format, import-linter, target surface);
  `test` = `make test` (pytest, sockets disabled, `-m "not live"`); `harness-check` = `make harness-check`
  (`validate-targets` + `migration-check` + `workload-check`); `pr-surface` = `make pr-surface`
  (path classification of a pull request's diff); `deps-allowlist`, `secret-scan`, `db-test`,
  `lock-check` as in the Makefile.
- **Layer** says where the gate lives: `surface` = `energy_platform.harness.surface` (run by
  `scripts/check_target_surface.py`, by `energyctl validate <id>` and by every MCP write);
  `manifest` = `energy_platform.contracts.manifest` structural validation; `admission` =
  `validate_manifest` (ADR-022); `fetch` = `energy_platform.fetch` runtime policy (ADR-026 layer 2);
  `ruff` = the rules in `pyproject.toml`; `pr` = `energy_platform.harness.pr_surface`; `workloads` =
  `scripts/check_workloads.py`; `mcp` = `energy_platform.mcp` tool guards.
- **Test** is the negative test. Tests that existed before this phase are cited where they are;
  new ones live under `tests/harness/`. A control (positive) case sits next to every negative one so
  that a gate which rejects everything is caught too.
- Rows are grouped by who trips them: A — target author (junior or agent, Route A); B — manifest and
  registry; C — network egress; D — repository and supply chain; E — agent tooling (MCP, sandbox).

## 1. The matrix

### A. Target authoring (ADR-005, ADR-027)

| ID | Failure mode | Layer | Gate (CI target) | Negative test |
|---|---|---|---|---|
| C-01 | **Hardcoded URL** in `parser.py` or any target `.py` (`https?://` literal) — fetch lives in the manifest | surface | `lint` | `tests/harness/test_target_surface.py::test_hardcoded_url_in_target_code_rejected` |
| C-02 | **Fetch code inside a target**: `http.client`, `socket`, `urllib`, `httpx`, `requests`, a `fetch.py` file | surface (positive import allowlist, positive file list) | `lint` | `test_target_surface.py::test_parser_import_outside_allowlist_rejected`, `::test_file_outside_surface_rejected` |
| C-03 | **Normalise code inside a target**: arithmetic on values (`*`, `/`, `//`, `**`), sign flip (unary `-` on a name or call), timezone conversion (`.astimezone(`, `tzinfo=`), interval shifting (`timedelta(`) | surface (AST) | `lint` | `test_target_surface.py::test_normalise_code_in_parser_rejected` (parametrised per construct) |
| C-04 | **Positional parsing**: integer-literal subscript in `parser.py` (`row[3]`); a manifest `source` that is a bare column number | surface (AST); manifest | `lint`; `harness-check` | `test_target_surface.py::test_positional_subscript_in_parser_rejected`; `tests/contracts/test_manifest_negative.py::test_numeric_source_is_positional_parsing` |
| C-05 | **`float()` on raw strings** (decimal comma sources, 01 §9) | surface (token) | `lint` | `test_target_surface.py::test_float_call_in_parser_rejected` |
| C-06 | **Duplicated utility**: a helper module in the target, or `parser.py` redefining a public function of `energy_platform.contracts` (`parse_decimal`, `interval_for_index`, …) | surface | `lint` | `test_target_surface.py::test_file_outside_surface_rejected` (a helper module under the target's tests), `::test_duplicated_platform_utility_rejected` |
| C-07 | **Unbounded retry / loop** in a target: `while True`, `time.sleep`, `tenacity` (not in the import allowlist); platform retries are bounded by `RetryPolicy.attempts` | surface; fetch | `lint`; `test` | `test_target_surface.py::test_unbounded_loop_in_parser_rejected`; `tests/fetch/test_client.py::test_5xx_exhausting_attempts_raises_fetch_failed` |
| C-08 | **Swallowed exception**: `except: pass`, bare `except`, blind `except Exception` | ruff S110, E722, BLE001 (targets and platform alike) | `lint` | `tests/harness/test_ruff_gates.py::test_swallowed_exception_rejected` |
| C-09 | **Naive datetime**: `datetime.now()` without `tz`, `utcnow()`, naive literals; a naive value in an observation | ruff DTZ + TID251; `EnergyObservation` | `lint`; `test` | `test_ruff_gates.py::test_naive_datetime_rejected`; `tests/contracts/test_observation.py` (naive rejected) |
| C-10 | **Suppression comment or test skip** in a target (`# noqa`, `# type: ignore`, `# pragma`, `pytest.mark.skip/xfail`, `importorskip`) | surface (token) | `lint` | `test_target_surface.py::test_suppression_or_escape_in_parser_rejected`, `::test_skipped_golden_test_rejected` |
| C-11 | **File outside the target surface** (`conftest.py`, helpers, stray files, non-empty `__init__.py`) | surface | `lint` | `test_target_surface.py::test_file_outside_surface_rejected`, `::test_non_empty_init_rejected`, `::test_stray_file_under_targets_root_rejected` |
| C-12 | **Third-party import in `parser.py`** (`lxml`, `pandas`, `requests`, relative import) | surface | `lint` | `test_target_surface.py::test_parser_import_outside_allowlist_rejected` |
| C-13 | **Placeholder left in a target** (`REPLACE_ME`, `TODO`) in `manifest.yaml`, a golden or `parser.py` — a scaffold is not a target | surface (token) | `lint` | `test_target_surface.py::test_placeholder_left_in_target_rejected` |
| C-14 | **Missing fixture** (no `fixtures/<name>/entry.json` + `blob`) | surface; pytest collection (`conftest.py`, ADR-020) | `lint`; `test` | `test_target_surface.py::test_missing_fixture_rejected`; `tests/harness/test_target_collection.py::test_target_without_fixture_fails_collection` |
| C-15 | **Missing golden** (no `tests/golden/*.yaml`) or no `tests/test_*.py` | surface; pytest collection | `lint`; `test` | `test_target_surface.py::test_missing_golden_rejected`; `test_target_collection.py::test_target_without_golden_fails_collection` |
| C-16 | **Empty or unchecked golden**: no expected rows, no `checked_by` | `GoldenFile` model (`energy_platform.contracts.golden`) via surface | `lint` | `test_target_surface.py::test_empty_golden_rejected` |
| C-17 | **Golden value disagrees with the fixture** (mapping-level data poisoning, ADR-008) | golden runner `energy_platform.harness.goldens`, auto-discovered by `tests/harness/test_goldens.py` | `test` | `tests/harness/test_goldens.py::test_wrong_golden_value_fails`, `::test_missing_expected_row_fails`, `::test_expected_quarantine_that_does_not_happen_fails` |
| C-18 | **Fixture is not a Bronze object** (blob hash ≠ `entry.payload_sha256`, entry unparsable) | surface via `bronze.load_fixture` | `lint` | `test_target_surface.py::test_fixture_not_a_bronze_object_rejected` |
| C-19 | **Target id mismatch** (`manifest.target_id` ≠ directory name) | surface; `energyctl validate <id>` | `lint`; `harness-check` | `test_target_surface.py::test_target_id_mismatch_rejected` |

### B. Manifest and registry (ADR-013, ADR-017, ADR-022, ADR-026)

| ID | Failure mode | Layer | Gate (CI target) | Negative test |
|---|---|---|---|---|
| C-20 | **Missing `license` / `terms_url`** (also how EPEX/Nord Pool stay out, ADR-008) | manifest | `harness-check` (`validate-targets`) | `tests/contracts/test_manifest_negative.py` (mandatory fields); `tests/harness/test_cli_harness.py::test_validate_rejects_missing_license` |
| C-21 | **Host not in `allowed_hosts`** (a URL in `fetch` on another host) | manifest; fetch `host_not_allowed` | `harness-check`; runtime | `test_manifest_negative.py` (host ∉ allowed_hosts); `tests/fetch/test_policy.py::test_host_not_in_manifest_allowlist` |
| C-22 | **Host not in the platform registry** (contributor-controlled allowlist is not admission) | admission `ADMISSION_REQUIRED`; fetch `host_not_registered` | `harness-check`; runtime | `tests/contracts/test_manifest.py` (admission gaps); `test_policy.py::test_host_in_manifest_but_not_in_registry` |
| C-23 | **Unregistered `dataset_id`** | admission → exit 2 | `harness-check` | `tests/cli/test_cli.py::test_validate_exit_codes_follow_the_status`; `test_cli_harness.py::test_validate_by_id_reports_admission_required` |
| C-24 | **Unregistered metric, or a metric marked "unknown" to pass** | admission | `harness-check` | `tests/contracts/test_manifest.py` (missing metrics listed) |
| C-25 | **Invented unit / dimension value** disagreeing with the registry | admission `INVALID` | `harness-check` | `tests/contracts/test_manifest.py` (unit must equal registry unit; fixed dimension value) |
| C-26 | **Secret in code or manifest** (token in a header, `Bearer …`, key in a URL) | manifest (credential-looking string rejected); `secret-scan` | `harness-check`; `secret-scan` | `test_manifest_negative.py` (credential in fetch block); `tests/harness/test_secret_scan.py` |
| C-27 | **`http` scheme** (without `allow_insecure` on both the manifest and the registry) | manifest; fetch `insecure_scheme` / `insecure_host_not_registered` | `harness-check`; runtime | `test_manifest_negative.py`; `test_policy.py::test_http_without_manifest_flag`, `::test_http_with_manifest_flag_but_registry_forbids` |
| C-28 | **YAML tricks in a manifest** (anchors, aliases, merge keys, tags, multiple documents) | manifest `ManifestSyntaxError` | `harness-check` | `test_manifest_negative.py` (YAML subset) |
| C-29 | **IP literal or explicit port in a URL** | manifest; fetch `ip_literal` / `port_not_allowed` | `harness-check`; runtime | `test_manifest_negative.py`; `test_policy.py::test_ip_literal_never_a_destination`, `::test_port_not_in_registry` |

### C. Network egress (A-7, ADR-026, ADR-027 §3–§4)

| ID | Failure mode | Layer | Gate (CI target) | Negative test |
|---|---|---|---|---|
| C-30 | **Outbound HTTP outside `energy_platform.fetch`** (`httpx`, `requests`, `urllib`, `http.client`, `socket`, `ssl` anywhere else) | ruff TID251 banned-api; import-linter (targets may not import `fetch`) | `lint` | `tests/harness/test_ruff_gates.py::test_http_client_outside_fetch_rejected`, `::test_fetch_package_is_the_only_exemption`; `tests/harness/test_ci_wrappers.py::test_import_linter_forbids_fetch_from_targets` |
| C-31 | **Redirect to an unlisted host** | fetch `redirect_to_unlisted_host` | runtime (`test`) | `tests/fetch/test_client.py::test_redirect_to_unlisted_host_fails` |
| C-32 | **Redirect to a private address** | fetch `private_address` on the hop | runtime | `test_client.py::test_redirect_to_private_address_fails` |
| C-33 | **Metadata / private / loopback / CGNAT resolution** (`169.254.169.254`, `10/8`, `127/8`, `100.64/10`, IPv6 counterparts), also as a proxy address | fetch `private_address` | runtime | `test_policy.py::test_private_and_metadata_addresses_rejected`, `::test_proxy_environment_is_honoured_but_metadata_proxy_is_refused`; `test_client.py::test_private_resolution_blocks_before_contact` |
| C-34 | **Too many redirects** (> 3) | fetch `too_many_redirects` | runtime | `test_client.py::test_more_than_max_redirects_fails` |
| C-35 | **Connected peer ≠ resolved address** (DNS rebinding) | fetch `peer_mismatch` / `peer_unknown` | runtime | `test_client.py::test_peer_mismatch_aborts_even_after_a_200`, `::test_transport_without_peer_info_needs_offline_flag` |
| C-36 | **Network call in a unit test** | `conftest.py` socket block (ADR-027 §4) | `test` | `tests/harness/test_network_block.py` |
| C-37 | **Live test selected in CI** / a CI step that bypasses Make | Makefile `-m "not live"`; workflow steps are `make …` only | `test` | `tests/harness/test_ci_wrappers.py::test_make_test_deselects_live`, `::test_ci_workflow_only_calls_make` |

### D. Repository and supply chain (ADR-006, ADR-008, ADR-016, ADR-022)

| ID | Failure mode | Layer | Gate (CI target) | Negative test |
|---|---|---|---|---|
| C-38 | **New dependency** (a package in `uv.lock` not in `deps-allowlist.txt`; lockfile drift) | `scripts/check_deps_allowlist.py`; `uv lock --check` | `deps-allowlist`; `lock-check` | `tests/harness/test_deps_allowlist.py::test_unlisted_package_fails` |
| C-39 | **PR touching outside `targets/<id>/`** while touching a target (mixed target/platform PR) | pr | `pr-surface` | `tests/harness/test_pr_surface.py::test_target_plus_platform_file_rejected`, `::test_git_diff_integration` |
| C-40 | **Registry edit inside a target PR** (`registry.py`, `hosts.py`, `deps-allowlist.txt`, `pyproject.toml`, `.github/`) | pr (special case of C-39, reported by name); CODEOWNERS (human) | `pr-surface` | `test_pr_surface.py::test_registry_edit_in_target_pr_rejected` |
| C-41 | **Two targets in one PR** | pr | `pr-surface` | `test_pr_surface.py::test_two_targets_in_one_pr_rejected` |
| C-42 | **Unpinned GitHub Action** (`uses:` without a 40-hex commit) | workloads | `harness-check` (`workload-check`) | `tests/harness/test_workloads.py::test_unpinned_action_rejected` |
| C-43 | **Mutable image tag** (`:latest`, tag without `@sha256:` in a Kubernetes manifest or a Dockerfile `FROM`) | workloads | `harness-check` | `test_workloads.py::test_mutable_image_tag_rejected`, `::test_dockerfile_from_without_digest_rejected` |
| C-44 | **Workload without resource requests/limits** (A-8; any container of a Pod-bearing kind) | workloads | `harness-check` | `test_workloads.py::test_container_without_requests_rejected`, `::test_container_without_limits_rejected` |
| C-45 | **Migration without a downgrade** (missing, `pass`, `raise NotImplementedError`) | `scripts/check_migrations.py` (static); up/down round trip on PostgreSQL | `harness-check` (`migration-check`); `db-test` | `tests/harness/test_migrations_gate.py::test_migration_without_downgrade_rejected`; `tests/store/test_migrations.py` |
| C-46 | **CODEOWNERS coverage lost** on the registries, allowlist, CI, ADRs | `tests/harness/test_ci_wrappers.py` reads `CODEOWNERS` | `test` | `test_ci_wrappers.py::test_codeowners_covers_the_protected_paths` |

### E. Agent tooling (ADR-006, ADR-007)

| ID | Failure mode | Layer | Gate (CI target) | Negative test |
|---|---|---|---|---|
| C-47 | **MCP tool outside the ADR-007 set** (a shell, `kubectl`, `terraform`, a merge tool) | mcp: the tool table is exactly the ADR-007 eight | `test` | `tests/harness/test_mcp.py::test_tool_set_is_exactly_adr_007` |
| C-48 | **MCP write outside the target surface** (another target, `energy_platform/`, `..`, absolute path, registry) | mcp `write_target_file` → surface classification and path confinement | `test` | `test_mcp.py::test_write_outside_surface_refused` (parametrised) |
| C-49 | **MCP write that plants a forbidden construct** (`# noqa`, `import http.client`, hardcoded URL) | mcp: the file is checked before it is kept; a rejected write leaves no file | `test` | `test_mcp.py::test_write_with_forbidden_content_is_rolled_back` |
| C-50 | **Network from the harness without opt-in** (`record_fixture` live, `energyctl record-fixture --live`) | mcp: server refuses unless started with `--allow-network`; CLI requires `--live` | `test` | `test_mcp.py::test_record_fixture_live_needs_server_opt_in`; `test_cli_harness.py::test_record_fixture_needs_live_or_file` |
| C-51 | **`open_pr` on a mixed, incomplete or red target** | mcp/`harness.pr`: bundle only when surface, admission and goldens are green and the session touched one target | `test` | `test_mcp.py::test_open_pr_refuses_when_gates_are_red` |
| C-52 | **`read_repository` escaping the checkout or reading secrets** (`../`, `.git/`, `.env`, keys) | mcp path confinement + deny-list | `test` | `test_mcp.py::test_read_repository_confined` |
| C-53 | **Level-3 action through tooling** (merge, push to `main`) | no tool exists; `scripts/apply_pr_bundle.py` never commits on `main` and never pushes without `--push` | `test` | `tests/harness/test_pr_bundle.py::test_apply_never_touches_main` |
| C-55 | **Restricted licence scheduled** (a manifest whose `license` starts with `restricted` reaching a CronJob) | `scripts/render_target_values.py` refuses at deploy time (P4-D11, P5-D3) | `helm-lint`, every deploy target | `tests/harness/test_render_target_values.py::test_restricted_license_is_refused_and_named` |
| C-56 | **CRD-backed kind in the default render** (`Cluster`, `PodMonitor`, `PrometheusRule`, `ExternalSecret`, `CiliumNetworkPolicy`) — the core chart must be tenant-clean (ADR-001 amend rule 2) | chart flags default off; `tests/harness/test_chart.py` | `test` (with helm), `helm-lint` | `test_chart.py::test_default_tenant_render_has_no_crd_backed_kind` |
| C-57 | **Pod not restricted-PSS clean** (root, no seccomp, privilege escalation, capabilities kept, host namespaces, hostPath, hostPort) (A-14) | `scripts/check_restricted_pss.py` on every rendered values set | `helm-lint` | `tests/harness/test_restricted_pss.py::test_each_restricted_rule_is_enforced` (parametrised), `test_chart.py::test_every_render_is_digest_pinned_resourced_and_restricted` |
| C-54 | **Unadmitted source answered by invention** instead of an admission request | `energyctl admission-request` / MCP `validate_target` return the Route B list; the registry is CODEOWNERS-only (C-40) | `harness-check`; `pr-surface` | `test_cli_harness.py::test_admission_request_lists_exactly_the_gaps` |

## 2. Gate inventory (what CI actually runs)

| Make target | Runs | Rows |
|---|---|---|
| `lint` | ruff (`DTZ`, `S`, `BLE`, `TID251`, …), ruff format, import-linter, `scripts/check_target_surface.py` | C-01…C-16, C-18, C-19, C-30 |
| `test` | pytest with sockets disabled; `tests/harness/test_goldens.py` auto-discovers every `targets/*/tests/golden/*.yaml`; `conftest.py` refuses an incomplete target at session start | C-07, C-09, C-14…C-17, C-31…C-37, C-46…C-53 |
| `harness-check` | `validate-targets` (`energyctl validate --all`), `migration-check`, `workload-check` | C-04, C-19…C-29, C-42…C-45, C-54 |
| `pr-surface` | `scripts/check_pr_surface.py` on `BASE…HEAD` (only on pull requests; says so and exits 0 otherwise) | C-39…C-41 |
| `deps-allowlist`, `lock-check` | allowlist and lockfile consistency | C-38 |
| `secret-scan` | credential-looking strings in tracked files | C-26 |
| `db-test` | store suite and migration up/down round trip on ephemeral PostgreSQL | C-45 |
| `helm-lint` | `helm lint` + `helm template` with tenant, local and all-flags values, each through `check_workloads` and `check_restricted_pss`; targets values generated by `render_target_values` | C-43, C-44, C-55, C-56, C-57 on the rendered chart |
| `live-smoke` (nightly, **never PR CI**) | `pytest -m live tests/live`: one bounded live read per committed target, shape only (ADR-020; Phase 4 P4-D10); `.github/workflows/nightly-live-smoke.yml` has `schedule` and `workflow_dispatch` triggers only | C-37 (proved by `tests/harness/test_ci_wrappers.py::test_live_smoke_runs_only_on_a_schedule_never_on_pull_requests`) |

Branch protection (`docs/branch-protection.md`) requires every one of these as a status check;
CODEOWNERS makes the registries, the allowlist, the Makefile, the CI files and the ADRs human-only.

## 3. Gates that are guardrails, not boundaries

ADR-027 §5: static checks stop the accidental bypass and make the deliberate one visible in a diff.
The boundary for constrained-agent mode is the sandbox (`deployment/sandbox/`): a container whose
only tools are the MCP server's, with no shell, no `kubectl`, no `terraform`, no secrets and egress
limited to the Git remote. Rows C-47…C-53 describe what the MCP server itself refuses; the sandbox
is what stops an agent from going around the server.

## 4. Adding a row

1. Name the failure mode in one line and cite the ADR or assumption it violates.
2. Pick the smallest layer that can reject it mechanically. Prefer an existing one (surface, manifest,
   fetch, ruff) over a new script.
3. Write the negative test first (`tests/harness/`), plant the failure, watch it pass the gate, then
   close the gate. Keep a positive control next to it.
4. Add the row here with the test path. A PR that changes a gate without changing this table is
   incomplete.

## 5. Deferred (recorded, not hidden)

| Item | Why not in this phase | Where it goes |
|---|---|---|
| Custom `parser.py` execution by the platform (loader) | dynamic import is banned platform-wide (ADR-027 §3, P2-D8); no committed target needs a custom parser (T1–T3, E1 are generic) | an ADR amending ADR-027 with one CODEOWNERS loader module, when a real source needs one |
| Layer-1 `NetworkPolicy` verification (ADR-026 §4, kind with a policy-enforcing CNI) | Phase 5 deployment work | Phase 5 local profile |
| Restricted Pod Security check on the rendered chart (`scripts/check_restricted_pss.py`) | the chart does not exist yet; the Makefile already calls the script when it does | Phase 5 |
| Rollback drill (ADR-016 §6) | needs a cluster | Phase 5 |
