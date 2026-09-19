# Validation and evidence

## Scope and preservation

The review covered all 41 Git-tracked files at commit `7d872eaa6e3b1f891bf199b803ae310b1ac6fa99`, including hidden CI/pre-commit configuration and the parsed lockfile. Initial tracked status was clean; no remote was configured. A SHA-256 baseline is in [codex-review/evidence/baseline-sha256.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/baseline-sha256.json>). Final comparison is recorded in [codex-review/evidence/preservation.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/preservation.json>).

All probe files and dependency/environment mutations were confined to an isolated copy under `/private/tmp/energy-codex-review-07qyg76h/`. The existing virtual environment was copied for offline checks. No original source, plan, roadmap, dependency file, target, hook, Git configuration or infrastructure was modified. No commit, PR, cluster operation, credential lookup, cloud API call or source polling campaign was performed. The only persistent repository addition is `codex-review/`.

Tools observed: Python 3.12.13, uv 0.11.7, pytest 9.1.1 and Ruff 0.16.8. The local shell had no Helm or Terraform executable. See [codex-review/evidence/tool-versions.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/tool-versions.json>).

## Baseline results

| ID | Command/check | Result | Interpretation |
|---|---|---|---|
| C00 | `make check`, isolated copy, `UV_OFFLINE=1`, fresh temporary uv cache | Failed before checks: uncached build dependency `hatchling` | Offline bootstrap limitation; normal online installation was not tested |
| C01 | `make -o sync check 'RUN=uv run --no-sync --offline'` | Exit 0 | Existing installed-tool checks pass; explicitly not a clean install |
| C02 | `make -o sync deps-allowlist 'RUN=uv run --no-sync --offline'` | Exit 0; 31 locked dependency names allowed | Tests name membership, not ADR approval, source trust or all build inputs |
| C03 | `make helm-lint` | Exit 0 with “no chart” skip | No Helm rendering, linting or restricted-PSS validation took place |
| C04 | `make terraform-validate` | Exit 0 with “no Terraform” skip | No Terraform validation or infrastructure test took place |
| C05 | `make demo` | Make exit 2; recipe exit 1 | Explicit unimplemented stub |
| C06 | `make local-up` | Make exit 2; recipe exit 1 | Explicit unimplemented stub |
| C07 | `make smoke-test` | Make exit 2; recipe exit 1 | Explicit unimplemented stub |
| C08 | `make new-target` | Make exit 2; recipe exit 1 | Explicit unimplemented stub |
| C09 | Existing scanner function over baseline current text files | No findings | Limited pattern scan, not a full credential/history audit |

C01 ran Ruff lint and format checks, import-linter, mypy and pytest. Import-linter reported 3 analyzed files, 0 dependencies and 2 kept contracts. Mypy accepted 8 source files. Pytest passed the **one existing version test**. These facts do not prove data correctness, target safety or HA.

Commands/output are preserved in [codex-review/evidence/checks.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/checks.json>) and `check-01.txt` through `check-08.txt` in this directory's evidence folder. The original bootstrap error is in [codex-review/evidence/check-00-bootstrap.txt](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/check-00-bootstrap.txt>).

## Negative probes

**P01 — Target collection and direct HTTP:** created `targets/review_probe/parser.py` in the isolated copy, with a typed function that constructs `http.client.HTTPSConnection` and uses its HTTP methods. Created `targets/review_probe/tests/test_rejected.py`, whose test always raises an assertion. The ordinary component check still returned 0; import-linter saw the enlarged package graph, mypy accepted 11 files, and pytest still ran just the original test. Explicit selection of the failing test returned 1. Collection listed only `tests/test_placeholder.py`. The HTTP function was never called.

**P02 — Scanner exclusions:** applied the unchanged scanner to a synthetic token-shaped marker. Bare marker: detected. The same marker plus an “example” comment: zero findings. The same marker inside an example-domain URL: zero findings. These were constructed fake values, not credentials taken from the environment.

**P03 — Lock consistency:** in the isolated copy only, changed a dev requirement to `pytest>=100` without updating the lock. Frozen sync with `--no-install-project` returned 0. That option avoided the unrelated uncached project build dependency. A follow-up `uv lock --check --offline` attempted resolution and failed because package metadata was absent from the temporary cache; it is **not** presented as a clean control proving a specific lock-mismatch diagnostic. The frozen-mode interpretation is independently supported by Astral's official documentation.

Probe output: [codex-review/evidence/adversarial-probes.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/adversarial-probes.json>), [codex-review/evidence/lock-consistency-probe.json](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/lock-consistency-probe.json>). The exact P01/P02 driver is preserved as text at [codex-review/evidence/adversarial_probes.py.txt](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/evidence/adversarial_probes.py.txt>). It is review evidence, not an installed test or a proposed patch. It relies on the local snapshot paths in `review-environment.json`; to repeat on another machine, prepare an isolated copy and environment first and update those paths. Do not run the probes against the working source tree.

## Coverage of the relevant behaviors

```text
Repository checks
  lint / types / listed import boundaries    exercised, pass
  package version                           exercised, pass
  dependency-name membership                exercised, pass
  scanner basic pattern                     exercised, pass
  scanner line exemptions                   exercised, bypass confirmed
  failing target test                       omitted by default collection
  direct target HTTP definition             accepted by current checks

Requested system
  manifest -> fetch -> Bronze -> parse
           -> mapping -> Silver -> query    not implemented
  duplicate/replay/correction handling       not implemented
  deploy -> smoke -> rollback -> restore    not implemented
  independent new-target contribution        not implemented
```

No numerical coverage percentage is claimed. A one-test green suite cannot sensibly be translated into a percentage of a system that has not been implemented.

## Evidence limits

Design findings are contract analyses, not reproduced failures of nonexistent platform code. Private infrastructure outputs in `docs/00-assumptions.md` were read as recorded historical evidence and were not re-run or certified current. Public documentation checks are listed separately in [codex-review/06-primary-source-checks.md](</Users/jalalhussein/Desktop/Desktop - Jalal’s MacBook Air/task-cze/codex-review/06-primary-source-checks.md>). The browsing tool could not retrieve the ČEPS pages/WSDL and could not parse the OTE XML WSDL; those are tool limitations, not proof of endpoint downtime. No service call, source latency, domain value series, migration, cluster failover or backup restoration was validated live.
