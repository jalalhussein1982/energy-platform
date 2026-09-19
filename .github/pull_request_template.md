## What

<!-- one paragraph -->

## Kind of PR

- [ ] **Target PR** — touches only `targets/<id>/` (manifest, optional parser, fixtures, goldens)
- [ ] **Platform PR** — touches `energy_platform/`, `deployment/`, CI or docs; has an ADR if it changes a decision

## Checklist (mirrors the future docs/05-constraint-matrix.md)

`[gate]` = a CI gate exists today; the rest are checked by the reviewer until Phase 3 adds their gate.

- [ ] No hardcoded URL, host or credential; hosts are in the manifest `allowed_hosts` and in the platform host registry (ADR-026)
- [ ] No naive datetime `[gate: ruff DTZ]`; every interval is aware; DST days (92/100) covered where relevant
- [ ] No swallowed exception `[gate: ruff S110/BLE]`, no unbounded retry, no positional parsing
- [ ] No outbound HTTP or socket outside `energy_platform.fetch` `[gate: ruff TID251 + target surface + unit-test socket block, ADR-027]`
- [ ] Target PR touches only the ADR-027 surface; `parser.py` imports only `energy_platform.contracts` and pure-data stdlib `[gate: make lint target-surface]`
- [ ] No new dependency, or: ADR filed **and** `deps-allowlist.txt` extended `[gate: deps-allowlist, lock-check]`
- [ ] Target has fixtures (Bronze objects) and golden values checked by hand; its tests are collected by default `[gate: pytest testpaths]`
- [ ] Manifest has `license`, `terms_url`, `allowed_hosts`; `dataset_id` and metrics are registered (ADR-022) — otherwise this PR is an admission request, not a target
- [ ] Any workload has resource requests/limits and a restricted-PSS security context (A-8, A-14)
- [ ] Any image reference is by digest, never a mutable tag (ADR-016)
- [ ] Any migration ships a downgrade script (ADR-016)
- [ ] No credential-looking string `[gate: secret-scan]`
- [ ] `make check` green locally `[gate: lint, lock-check, type, test]`

## Decisions touched

<!-- ADR ids, or "none" -->
