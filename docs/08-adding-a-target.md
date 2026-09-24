# Adding a target

This page is enough to add a data source ("a target") to energy-platform without knowing the
rest of the repository. It is written for a junior engineer and for a coding agent alike. Every
command below was run while this page was written (2026-09-23, on a scratch copy of the E1
target, `targets/ote_dam`).

## 1. The one rule

A target is **declared, not coded**. You write a YAML manifest, record sample payloads
("fixtures"), and write the expected values by hand ("goldens"). You never write fetch code or
normalisation code: the platform fetches, parses and maps. Your pull request touches
**`targets/<id>/` and nothing else** (CI rejects anything outside it: `make pr-surface`).

Two routes exist (ADR-022), and step 3 tells you which one you are on:

| Route | When | What you deliver |
|---|---|---|
| **A — add an adapter** | the source's dataset, metrics, units and host are already admitted | a PR with `targets/<id>/` only |
| **B — ask for admission** | anything is missing: `validate` says `ADMISSION_REQUIRED` | a PR with `docs/admissions/<id>.md` only, then stop |

Stopping with an admission request is the correct outcome for an unadmitted source, not a
failure. Inventing a unit, editing the registry, or widening an allowlist to make validation pass
is the failure.

This is a contributor task, not a development phase: do not write a phase plan and do not edit
`docs/plans/`, `docs/03-roadmap.md` or `docs/progress.md` (maintainer bookkeeping), not even
locally.

## 2. Setup

```bash
git clone https://github.com/jalalhussein1982/energy-platform.git && cd energy-platform
make sync           # uv sync --frozen --group dev (Python 3.12, uv 0.11)
make check          # must be green before you start
```

Every command below is written as `ep …`, meaning:

```bash
uv run python -m energy_platform.cli …      # the same CLI as `energyctl …`
```

(`energyctl` is the installed console script; `python -m energy_platform.cli` always works.)
Unit tests run with the network disabled; only commands that say `--live` reach the internet.

## 3. Find what is admitted, and choose the route

1. Look up your source: search `docs/admissions/` and `energy_platform/contracts/registry.py`
   for the endpoint, host or operation name. An admission record
   (`docs/admissions/<id>.md` with status **ADMITTED**) gives you the `dataset_id`, the metrics
   with their units and sign rules, the source field each metric comes from, the fields you must
   ignore, and the identity key (including whether a `version` is part of it).
2. The registry entry is the law: your manifest's metric names and units must equal it exactly.
   The host must be in `energy_platform/contracts/hosts.py`.
3. Nothing found, or something missing? You are on **Route B** — go to §10.

## 4. Scaffold

```bash
ep new-target my_source --modality soap-xml --dataset ote.dam --host www.ote-cr.cz
```

- `target_id`: lower snake case, it becomes the directory name.
- `--modality`: `soap-xml` | `dated-file` | `html-table` | `rest-json` | `rest-xml`.
- `--dataset`: a registered `dataset_id`; the scaffold then fills the metric names and units.

It writes exactly the allowed surface:

```text
targets/my_source/
  __init__.py
  README.md                  ← describe the source and the fixture table
  manifest.yaml              ← REPLACE_ME everywhere a decision is yours
  tests/__init__.py
  tests/test_golden.py       ← leave as generated
  tests/golden/ordinary_day.yaml
```

A target is not complete while any `REPLACE_ME` (or `TODO`/`FIXME`) remains: CI refuses it.

## 5. Fill the manifest

Copy the shape of the closest existing target and change only what differs:

| Existing target | Shows |
|---|---|
| `targets/ote_intraday_market` (T1) | SOAP, `period_index` time, absent element = NULL, `ignore_fields` |
| `targets/ote_dam` (E1) | SOAP day-ahead: `{next_delivery_day}`, four metrics, a dimensionless flag |
| `targets/ceps_load` (T3) | SOAP with an attribute-shaped response and a `version` identity dimension |
| `targets/ote_intraday_market_xlsx` (T2) | a dated file (XLSX) with human column headers |

Field by field:

| Field | What to write |
|---|---|
| `description` | one line: source, operation, resolution |
| `license`, `terms_url` | the source's terms, quoted; say whether redistribution is allowed (it decides your fixtures, §6) |
| `allowed_hosts` | the host(s) from the admission; nothing else |
| `cadence.cron` | how often to fetch (Europe/Prague); `correction` re-polls past days when the source revises |
| `history.max_age` | how far back the source serves data (ISO duration) |
| `fetch.<modality>` | URL, SOAP action and body template with `{start_date}`-style parameters; `params` render them from `{delivery_day:%Y-%m-%d}`, `{next_delivery_day:…}`, or, for a whole earlier month, `{month_start[k]:…}` / `{month_end[k]:…}` (*k* months back, 0…12); nothing else, and no attribute access |
| `contract` | `dataset_id`, `source_transport`, `decode`, and the metric list |
| `mapping.dimensions` | the constant identity dimensions (e.g. `bidding_zone: CZ`) |
| `mapping.time` | `kind: period_index` with `date`, `index`, `resolution` (each `{source: <field>}`, `{constant: …}` or `{context: delivery_day}`), or `kind: timestamp` |
| `mapping.source_version` | `null`, `{constant: …}`, or `{source: <field>}` when the identity key has `version` |
| `mapping.metrics.<m>` | `source` (the element, attribute or column header), `unit` (exactly the registry unit), `sign: as_published`, `decimal_separator: dot` or `comma` |
| `mapping.ignore_fields` | every response field you deliberately do not map (they raise no warning) |

Rules the platform enforces for you, which you must still get right in the goldens:

- An absent element is NULL, never zero. A published `0` is a value.
- Czech sources often use a decimal comma: declare it, never convert by hand.
- Every instant is timezone-aware. Delivery days have 96 quarter-hours, **92** on the spring DST
  day and **100** on the autumn DST day; period index 1 starts at local midnight.

Check it:

```bash
ep validate my_source
```

Exit 0 `OK`, 1 `INVALID` (the JSON lists each error and the rule, e.g. `05 C-14`), 2
`ADMISSION_REQUIRED` (§10). Before fixtures exist it reports exactly that they are missing.

## 6. Record fixtures

A fixture is a Bronze object — the payload plus its capture entry — under
`targets/<id>/fixtures/<name>/`. Two ways:

```bash
ep record-fixture my_source --name ordinary_day --live            # fetch once through the platform
ep record-fixture my_source --name ordinary_day --from-file saved.xml \
   --scheduled-for 2026-09-20T12:00:00+00:00                      # wrap a saved payload offline
```

If the terms do not allow redistribution (OTE: refused on 2026-09-24, so synthetic for good — 06 §1.4;
ČEPS: not answered yet), commit **synthetic** fixtures
with the real shape: a `--live` recording contains the real payload, so use it only to learn the
shape, then delete that fixture directory; write a copy that keeps the structure and element
names with changed values, and wrap it with `--from-file`. Fixtures are immutable: a new case
gets a new name.

Record at least: an ordinary day; the spring and autumn DST days if the source is per period; an
empty or not-yet-published answer; a case with negative or zero values if the metric allows them;
and any quirk the admission names (decimal comma, a fault answered with HTTP 200).

## 7. Write the goldens by hand

One file per fixture in `tests/golden/<fixture>.yaml`. The values come from **reading the
fixture** (for example `grep -n '<Price>' targets/my_source/fixtures/ordinary_day/blob`), never
from running the platform and copying its output — the golden is what catches a wrong mapping.

```yaml
fixture: ordinary_day
checked_by: "your name, date, how: values read from fixtures/ordinary_day/blob"
expect:
  row_count: 384                      # items × metrics, NULLs included
  quality_events: [partition_status]  # the events the document should raise
  rows:
    - {delivery_start_utc: 2026-09-21T00:00:00+02:00, resolution: PT15M, metric: price, value: "79.00"}
    - {delivery_start_utc: 2026-09-21T23:45:00+02:00, resolution: PT15M, metric: volume_total, value: "2532.000"}
```

- `delivery_start_utc` is any aware timestamp (a local offset is fine); `value` is a **quoted**
  decimal or `null`; YAML floats are refused.
- Add `source_version: "…"` to each row when the dataset's identity includes `version`, and
  `period_index` when it helps a reviewer.
- A fixture the platform must refuse gets `expect: {quarantine: "<part of the reason>"}`; an
  empty answer gets `expect: {row_count: 0}`.
- Pick rows that would catch mistakes: the first and last period, a DST hour, a NULL, a negative.

Run everything the CI will run for your target:

```bash
ep run-target-tests my_source
```

```text
surface: OK
golden ordinary_day.yaml (ordinary_day): OK, 384 rows
pytest: exit 0
```

## 8. Write the target README

Say what the source is, where the contract comes from (the admission record), how often it is
fetched and why, and a table of fixtures with what each demonstrates and its expected outcome
(see `targets/ote_dam/README.md`).

## 9. Open the pull request (Route A)

```bash
make check                                  # the whole repository, green
make pr-surface BASE=main                   # your change touches targets/my_source/ only
ep pr-bundle my_source                      # refuses unless every gate is green; never pushes
uv run python -m scripts.apply_pr_bundle .energy_platform/outbox/my_source-<stamp>.json --push
gh pr create --base main --head target/my_source
```

Or with plain git: branch `target/my_source`, commit only `targets/my_source/`, push, open the PR.
`main` is protected: the PR needs the 12 CI checks and a code-owner review. In the PR
description say how you checked the goldens.

## 10. Route B — ask for admission, then stop

When `ep validate my_source` exits 2 (`ADMISSION_REQUIRED`), it lists what is missing (dataset,
metrics, hosts). Then:

```bash
ep admission-request my_source              # writes docs/admissions/my_source.md
```

Fill every `REPLACE_ME` in that file with what you know from the source (endpoint, terms,
proposed units, what NULL and the sign mean, a short sample of the response shape). Open a PR
that contains **only** `docs/admissions/my_source.md`; do not commit `targets/my_source/`. A
maintainer decides: admission (registry, host registry and the admission register, under code
ownership) or refusal. Only after an admission do you continue with Route A.

## 11. With an agent (MCP)

`ep mcp-serve` exposes the same path as eight tools: `read_repository`, `inspect_target`,
`scaffold_target`, `write_target_file`, `validate_target`, `record_fixture`,
`run_target_tests`, `open_pr`. Writes outside `targets/<id>/` are refused, live fetches need the
server started with `--allow-network`, and `open_pr` only prepares the bundle of §9.

## 12. When something is refused

| Message contains | Meaning | Fix |
|---|---|---|
| `placeholder left in the target` (C-13) | a `REPLACE_ME`, `TODO` or `FIXME` remains | decide the value (§5) |
| `ADMISSION_REQUIRED` | dataset, metric or host not admitted | Route B (§10) |
| `unit … must be the registry unit` | your unit differs from the registry | use the registry unit exactly; never convert |
| `no fixture` / `fixture … does not exist` (C-14, C-15) | missing fixture or a golden pointing nowhere | §6 |
| `hardcoded URL`, `float()`, `import …` in a `.py` | code where declaration belongs | move it to the manifest; targets have no fetch or maths |
| `not a target PR` / a file outside `targets/<id>/` | your change set is too wide | keep only `targets/<id>/` |
| `positional access` / `positional parsing` (C-04) | a source given as a column number or index | name the element or header |
| golden `value … expected …` | the mapping and your reading of the fixture disagree | re-read the fixture; fix the manifest, not the golden, unless the golden is wrong |

## 13. Checklist

- [ ] Route decided from the admission record and `ep validate`
- [ ] No `REPLACE_ME` left; units equal the registry; unmapped fields in `ignore_fields`
- [ ] Fixtures: ordinary day, DST days, empty, edge values; synthetic if redistribution is not allowed
- [ ] Goldens read from the fixtures by hand; `checked_by` says how
- [ ] `ep run-target-tests <id>` green; `make check` green; `make pr-surface BASE=main` green
- [ ] Target README with the fixture table
- [ ] PR touches `targets/<id>/` only
