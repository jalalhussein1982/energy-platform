## What

<!-- one paragraph -->

## Kind of PR

- [ ] **Target PR** — touches only `targets/<id>/` (manifest, optional parser, fixtures, goldens)
- [ ] **Platform PR** — touches `energy_platform/`, `deployment/`, CI or docs; has an ADR if it changes a decision

## Checklist (mirrors docs/05-constraint-matrix.md; CI enforces each row mechanically)

- [ ] No hardcoded URL, host or credential; hosts are in the manifest `allowed_hosts`
- [ ] No naive datetime; every interval is aware; DST days (92/100) covered where relevant
- [ ] No swallowed exception, no unbounded retry, no positional parsing
- [ ] No outbound HTTP outside `energy_platform.fetch` (A-7)
- [ ] No new dependency, or: ADR filed **and** `deps-allowlist.txt` extended
- [ ] Target has fixtures (Bronze objects) and golden values checked by hand
- [ ] Manifest has `license`, `terms_url`, `allowed_hosts`
- [ ] Any workload has resource requests/limits and a restricted-PSS security context (A-8, A-14)
- [ ] Any image reference is by digest, never a mutable tag (ADR-016)
- [ ] Any migration ships a downgrade script (ADR-016)
- [ ] `make check` green locally

## Decisions touched

<!-- ADR ids, or "none" -->
