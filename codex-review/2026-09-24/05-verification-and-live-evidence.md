# Verification record and live evidence

## Snapshot and preservation

Source: `1701ac77175113d744abaad0514489711ed2b1d4`, `main`, initially clean. Reviewed 2026-09-24; live observations approximately 14:20–14:27 UTC. These are snapshots, not continued monitoring.

The [baseline](evidence/baseline.json) contains SHA-256 hashes of 573 tracked files. The [final preservation result](evidence/preservation.json) records the comparison. The source archive and copied installed environment used for broad tests were `/private/tmp/energy-review-ho5i3iiz`; the original environment was not synchronized. A second, empty environment `/private/tmp/energy-review-cleanvenv` independently tested locked installation. Audit scripts use `.py.txt` so evidence does not enter application lint/test discovery.

No source fix, commit, push, PR creation, merge, deploy, Terraform apply, cloud resource change, Kubernetes resource mutation, destructive live drill, or production database write occurred. Reading APIs may create normal provider audit logs. Tests created temporary local databases and scratch files; their helpers cleaned those up. Temporary source/virtualenv copies remain outside the application directory.

## Fresh local checks

Make commands ran in the isolated copy with a review-specific `UV_CACHE_DIR` and `UV_PROJECT_ENVIRONMENT`. Both application DSN variables were unset before database tests. Credentials were never printed.

| Verification | Fresh result | Evidence and limit |
|---|---|---|
| `make check` | **887 passed, 25 skipped, 8 deselected**; lint/format/import layers/lock/mypy/harness passed | [Full log](evidence/make-check-network.log). 194 source files typed. |
| Empty-env `uv sync --frozen --group dev` | **PASS** | [Bootstrap](evidence/clean-dependency-bootstrap.log). Python 3.12.13; existing host system dependencies, not a clean OS. |
| `make db-test` | **26 passed, 894 deselected** | [Additional checks](evidence/additional-checks-network.log). Ephemeral PostgreSQL 18.4 over a local Unix socket. |
| `make demo` | **PASS** | Same log. Migration/capture/process/query on synthetic fixtures and disposable PostgreSQL. |
| `make deps-allowlist secret-scan` | **PASS** | Same log. All 57 locked packages allowlisted. This is not an exhaustive historical credential audit. |
| `make helm-lint` | **PASS**, tenant/local/all-flags and workload/restricted-PSS checks | Same log. No actual operator admission or CNI test. |
| `make terraform-validate` | **PASS**, both roots valid; **3 hcloud + 3 OpenStack mock tests** | [Log](evidence/terraform-validate.log). Backend disabled, no real cloud plan/apply. |
| `make live-smoke` | **7 passed** | [Log](evidence/live-source-smoke.log). Bounded source reads, temporary responses removed by the tests. |
| Agent/tooling subset | **196 passed** | Exact command in [agent report](02-agent-constraints.md). |
| Deployment static subset | **47 passed** | Exact command in [deployment report](04-deployment-and-ha.md); [four additional render records](evidence/deployment/static-probe-summary.json). |
| Independent fixture derivation | **42 positive fixtures / 215 golden sample values and UTC instants matched** | [Original](evidence/independent-fixture-check.log), [parent rerun](evidence/independent-fixture-parent-rerun.json). Expected metric-row counts total 45,493, not 45,493 live delivery periods. |
| Data counterexamples | **Eight groups reproduced** | [Original](evidence/data-correctness-probes.log), [parent rerun](evidence/data-correctness-independent-rerun.log). Exit 0 means defects reproduced. |
| SQL-backed counterexamples | **DC-01/02/03/04/05/08 reproduced on PostgreSQL** | [Log](evidence/postgres-counterexamples.log). Actual SQL store in disposable scratch schemas. |
| Agent counterexamples | **AE-01/03/04 reproduced**, with positive control and zero socket attempts | [Original](evidence/agent-constraint-probes.json), [parent rerun](evidence/agent-constraint-independent-rerun.json). AE-02 is a caller/callee workflow contradiction. |

Initial offline bootstrap failed because the review cache lacked `hatchling`; authorized network access resolved it. The first ephemeral database attempt was blocked by the sandbox's shared-memory restriction; it succeeded with permission to start the temporary instance. See [offline attempt](evidence/make-check.log) and [sandbox DB attempt](evidence/additional-checks.log). These are environment restrictions, not application defects. GitHub connectivity also succeeded on the authorized read-only retry.

**Live-smoke limit:** `tests/live/test_smoke.py:40-47` asserts required fields only for records found. Empty output is accepted. A renamed required field can cause zero recognized records and a vacuous pass; AE-01 reproduces that recognition failure with a synthetic payload. Seven passed checks do not prove seven nonempty, correct, fresh data streams or detection of every schema change.

## GitHub

The repository is public and active, default branch `main`.

- [HEAD CI run 36004869532](https://github.com/jalalhussein1982/energy-platform/actions/runs/36004869532): all 12 jobs successful. [Job evidence](evidence/github-ci-head.json).
- [Latest applicable deploy 36003743511](https://github.com/jalalhussein1982/energy-platform/actions/runs/36003743511): successful at `45b46ec6fbe44513919e0b87b561a0e1474f09d4`. [Evidence](evidence/github-latest-deploy.json). Reviewed HEAD differs by a README-only update.
- Latest scheduled live smoke observed: [run 35975121335](https://github.com/jalalhussein1982/energy-platform/actions/runs/35975121335), successful. The audit separately reran source smoke.
- [Branch protection](evidence/github-branch-protection.json): 12 required checks, up-to-date branches, one approval, code-owner review, stale approvals dismissed, conversation resolution; no force pushes/deletions. `enforce_admins=false`, matching the disclosed administrator bypass.
- [PR snapshot](evidence/github-prs.json): real admission/target PR records. This audit did not repeat a blind authoring trial or inspect all historical agent transcripts.

Deploy depends on its image job, not the separate CI workflow (`.github/workflows/deploy-demo.yml`). For ordinary protected PR merges, prior checks are the boundary. Administrator direct pushes/manual dispatch can bypass that relationship; no failing deployment was inferred or induced.

## Live Hetzner/Kubernetes

The existing demo kubeconfig was used for read-only APIs; no Secret resource was retrieved. Evidence: [nodes](evidence/live-nodes.json), [workloads](evidence/live-workloads.json), [policies](evidence/live-policies.json), [all-namespace pod names](evidence/live-all_workload_names.txt).

- Two Ready nodes: one control plane and one agent, k3s `v1.36.4+k3s1`, Ubuntu 24.04.4.
- One PostgreSQL replica pinned to `energy-platform-demo-server`; one ready exporter.
- Seven capture definitions, with process/backfill/correction and shared maintenance jobs.
- Application image: `ghcr.io/jalalhussein1982/energy-platform@sha256:1bde92efb00939d597332c12e2f873ea4f8a5d7ad6c74d2d492e3b5816ffc526`.
- Recent captures, processes, WAL shipment and replication completed. Monthly/final capture schedules had not fired. Their maintenance jobs completing does not establish produced data.
- A historical scheduled restore was OOMKilled, manual attempt 2 failed, and manual attempt 3 completed. These are retained history, not evidence the current image still has the fixed OOM. [Successful drill log](evidence/restore-drill-manual-3.log) was read, not rerun.
- Repeated XLSX recapture failures identify a **provider 404 for the 22 September file**, while 21/23 September requests succeed unchanged. [Selected log](evidence/energy-platform-recapture-ote-intraday-market-xlsx-29837649.log). This is not presented as a newly discovered code regression.
- No Prometheus/Alertmanager pod was present. An external receiver could exist; active scraping/paging was not verified.

## Live database

Aggregate queries ran through the existing PostgreSQL container with `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=20000'`, `psql -X -v ON_ERROR_STOP=1`, and explicit `BEGIN READ ONLY; ... SELECT ...; COMMIT;`. No source price/value rows, passwords or environment dump were requested.

[Data summary](evidence/live-data-summary.txt) and [semantic summary](evidence/live-semantic-summary.txt) preserve output.

| Data group | Historical metric rows | Observed state |
|---|---:|---|
| ČEPS SOAP RT | 12,798 | Recent fetch/process; freshness late, 3/4 prior-hour periods. |
| OTE day-ahead SOAP | 1,536 | Current/next-day data; complete. |
| OTE intraday SOAP | 11,018 | Recent, rolling-day partial. |
| OTE intraday XLSX | 82,656 | Recent; separate historical correction 404. |
| OTE settlement v0 | 864 | 21–23 September data. |
| Monthly v1 / final v2 | 0 | No corresponding runs or v1/v2 observations yet. |

Total: **108,872 historical metric rows**. The canonical view selected XLSX for 288 price_vwap and 288 volume_total rows, despite SOAP ownership; 96 of each remained SOAP. The repaired 22 September had no current XLSX rows and retained 192 SOAP rows. This verifies the removal's current effect, not replay safety (DC-07).

Missing-capture ledger rows were present, including historical/pre-deployment and source-unavailable dates. They are not automatically equated with lost successful live captures. The correction findings have separate concrete reproductions.

## Unverified boundaries

No new clean-machine cluster bring-up, node/control-plane/database failover, B-only live restore, full infrastructure recovery, bucket-lock enforcement test, first-packet CNI test, alert-delivery test, CNPG/external-mode deployment, real cold-tier movement, provider permission confirmation or week-long latency campaign was performed. Historical documented exercises are credited as such, not relabeled as fresh independent verification.
