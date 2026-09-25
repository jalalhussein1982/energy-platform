# Verification record

Review date: 25 September 2026, Europe/Prague. Live evidence was collected across the UTC date boundary. Reviewed HEAD: `bc87c585ce8a61be2995d0b0b1b283f87c2032a6`.

## Preservation and scope

Before reviewing, 71 existing files under `codex-review` were moved to `archive/before-2026-09-24T23-21-51Z/`. SHA-256 checks established that their contents were preserved; [the manifest](evidence/archive-manifest.json) records paths and hashes. Old findings are historical, not assumed current.

[The source baseline](evidence/source-baseline.json) records 566 files outside `codex-review`, including the existing untracked final report. [The final preservation check](evidence/preservation.json) records the end-of-review comparison. Application code, targets, deployment files and the supplied final report were not edited. No commit, push, merge, deployment, infrastructure apply, cluster write, secret retrieval or production-database mutation was performed.

Review coverage emphasized contracts/ADRs and contributor instructions; target validation and PR boundaries; fetch and network controls; Bronze/capture/reconciliation; parser/mapping and version identity; PostgreSQL ordering, occurrences and invalidations; gaps/backfill/replay/drills; chart, IaC and release controls; the final report and recorded acceptance evidence. This is not a claim to have manually read every source line or proved the absence of all possible defects.

## Fresh checks

| Check | Result | Evidence |
| --- | --- | --- |
| `UV_CACHE_DIR=/private/tmp/energy-review-uv-cache UV_OFFLINE=1 make check` | Exit 0; 928 passed, 32 skipped, 8 deselected; type/lint/import/surface/lock/migration/workload checks and all seven target validations passed | [Log](evidence/make-check.log) |
| `make db-test` using the repository temporary PostgreSQL helper, inherited DSNs cleared | Exit 0; 33 passed, 935 deselected; PostgreSQL 18.4 | [Log](evidence/db-and-demo.log) |
| `make demo` using a separate temporary PostgreSQL database | Exit 0; three fixture-backed sources processed, same-input replay no-ops, current-view queries succeeded | [Same log](evidence/db-and-demo.log) |
| `make helm-lint deps-allowlist secret-scan` | Exit 0; tenant/local/all-flags chart lint and restricted-pod/resource checks passed; 57 locked packages allowlisted; scan passed | [Log](evidence/static-extra-gates.log) |
| Terraform formatting, backend-disabled initialization and validation; `terraform test` in hcloud/openstack roots | Both configurations valid; three mock tests per root, six total passed | [Formatting](evidence/terraform-fmt.log), [validation/tests](evidence/terraform-mock-validation.log) |
| Independent fixture interpretation, without importing `energy_platform` | PASS; 42 positive fixtures across seven targets, 45,493 native rows counted, 215 sampled values and UTC instants checked | [Result](evidence/independent-fixture-check.json), [checker](archive/before-2026-09-24T23-21-51Z/2026-09-24/evidence/independent-fixture-check.py.txt) |

The initial sandboxed PostgreSQL attempts could not allocate shared memory on macOS. They were rerun successfully outside that restriction using temporary local Unix-socket databases. The first logs are retained as environmental failures, not counted as application failures. Terraform used a temporary copy of tracked source, mock cloud providers and no real state/tfvars or cloud apply. A formatting/lint advisory about a chart icon was not treated as a finding.

## Additional defect probes

These are synthetic counterexamples using committed fixtures and the existing runtime. They perform no provider requests. Their successful exit means the expected defect and control were reproduced; it does not mean the application passed that scenario.

| Probe | Result on memory and PostgreSQL | Evidence |
| --- | --- | --- |
| Successful capture starting 25 seconds late | Exact scheduled slot becomes missing; backfill fetches again | [Script](evidence/schedule_probe.py), [memory](evidence/schedule-probe.json), [PostgreSQL](evidence/schedule-probe-postgres.json) |
| Shared dataset with daily/monthly targets | Fresh drill reports 8,916 missing versions before the second target is rebuilt; identical warm second pass succeeds | [Script](evidence/recovery_probes.py), [memory](evidence/recovery-probes.json), [PostgreSQL](evidence/recovery-probes-postgres.json) |
| Harmless mapping revision with old/new history | Fresh current-manifest rebuild produces 192 versions while live synthetic store holds 384; old derivation missing | Same recovery script/results |
| Core-only semantic correction under unchanged package version | Replay is a no-op; control version bump produces corrected output and a new derivation | [Script](evidence/derivation_probe.py), [memory](evidence/derivation-probe.json), [PostgreSQL](evidence/derivation-probe-postgres.json) |

Run a memory probe from repository root with `PYTHONPATH=. .venv/bin/python codex-review/evidence/schedule_probe.py` (substitute the other script names). To reproduce against temporary PostgreSQL:

```sh
env -u ENERGY_PLATFORM_DSN -u ENERGY_PLATFORM_TEST_DSN \
  REVIEW_USE_POSTGRES=1 PYTHONPATH=. \
  scripts/with_postgres.sh .venv/bin/python codex-review/evidence/schedule_probe.py
```

[The shared helper](evidence/probe_store.py) rejects TCP/ordinary database destinations and accepts only the temporary `/tmp/ep-pg.*` Unix-socket connection generated by the repository helper. Probe schemas are isolated. Synthetic altered values must not be described as observed production values.

## Fresh read-only live observations

- The reviewed HEAD had successful [CI](https://github.com/jalalhussein1982/energy-platform/actions/runs/36065642131) and [demo deployment](https://github.com/jalalhussein1982/energy-platform/actions/runs/36065642514). [Saved run metadata](evidence/github-runs.json).
- [Branch protection](evidence/github-protection.json) required 12 checks, strict up-to-date status and one approving code owner. Administrator enforcement was disabled. This is a real contributor gate, not a technical prohibition on every action a repository owner can take.
- Read-only Kubernetes node, workload, pod, CronJob and Job listings confirmed two ready nodes, a single PostgreSQL instance, 33 unsuspended CronJobs and recent backup/replication activity. [Nodes](evidence/live-nodes.log), [workloads](evidence/live-workloads.log), [pods](evidence/live-pods.log), [CronJobs](evidence/live-cronjobs.log), [Jobs](evidence/live-jobs.log).
- A recent OTE process job reported successful insertion of 10 rows. [Log](evidence/live-process.log). This proves a recent successful processing execution, not every target's full live history.
- The retained scheduled restore job started `2026-09-24T01:30Z` and failed. A later manual job completed at `03:26:42Z`; [its log](evidence/live-restore-log.txt) reports successful physical-backup and raw-rebuild phases, approximately 777 and 1,216 seconds respectively. That is useful real recovery evidence. It does not prove an uninterrupted history of successful nightly drills, provider-loss RTO or complete equality of all live database state.
- Monthly/final capture jobs had no previous scheduled run at the snapshot. Their drill entries had zero replica captures but inherited same-dataset version counts; those entries do not exercise populated monthly targets. See R5.

No fresh node kill, provider-loss test, clean-clone full deployment, production replay, restore, live capture sweep or alert-injection test was run. Existing operations/acceptance records are identified as recorded evidence, not fresh verification. Source-use statements were assessed as repository policy; this was not an independent legal determination of operator permissions.

## Independent challenge

After the main investigation, two agents received focused briefs without inheriting the full conversation. One challenged the four data/recovery mechanisms; the other challenged HA, alerting and delivery claims. They were instructed to find reasons to reject or narrow findings, not to produce a quota of issues. Their reports are [data](agent-data-challenge.md) and [delivery](agent-delivery-challenge.md). The root reviewer reconciled their conclusions, retained the qualifications and remained responsible for the final assessment.
