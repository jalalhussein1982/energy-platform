# Response to the Codex review of the completed platform (2026-09-25, codex-astra)

| | |
|---|---|
| Reviewed snapshot | `bc87c58` (the deployed commit: demo revision 24) plus the untracked `docs/overview/final-report.md` |
| Review material | `codex-review/` (README, 01–03, the two challenge reports, `evidence/`) — committed verbatim; the reviewer moved the two earlier rounds under `codex-review/archive/before-2026-09-24T23-21-51Z/` with a SHA-256 manifest, and they stay there |
| Independent check | all four probe scripts rerun on the maintainer's machine 2026-09-25 before this response, on the memory store and on the temporary PostgreSQL helper exactly as `03-verification.md` says: **R2, R4, R5 and R6 all reproduce** (exit 0 on both backends: the phantom gap and the second fetch; the no-op replay of a core-only correction with `0.0.2` as the control; 8 916 "missing" on an empty scratch and a pass on the warm one; 192 old-derivation versions missing after a harmless mapping revision). R1 and R3 are readings of the rendered charts and the live inventory; both check out. |
| This document | one verdict per finding, the reasoning, and where the finding is closed |
| Plan | `docs/plans/phase-13.md` |

The reviewer's overall verdict is accepted: the ingestion, the contributor model and the
infrastructure code are delivered; the high-availability and recovery *claims* of the final
report are stronger than what the deployed environment and the drill's comparison rule prove.
Nothing in the review is declined. Two of the six findings are design gaps that the previous
round did not reach (R4's release identity, R6's rebuild guarantee), two are defects in the
runtime with a live effect (R2 on every scheduled capture since the demo went live, R5 waiting
for the first monthly capture), one is a missing piece the alert rules have assumed since
ADR-037 (R3), and one is the demo's topology stated by ADR-028 but never turned into a boundary
the final report respected (R1). The final report is revised row by row in Phase 13 and not
before the fixes exist, so that it describes what holds.

One housekeeping change is made alongside the review material: the reviewer's probe scripts
are `.py` files this round (last round's were `.py.txt`), so ruff would lint them and
`make check` would be red with the review in the tree. `pyproject.toml` scopes ruff with
`extend-exclude = ["codex-review"]`; no rule changes, the scripts stay as written and runnable
by the command in `03-verification.md`.

## Verdicts — the six findings (`01-deep-review.md`)

### R1 — the live deployment is recoverable, but has single-node availability dependencies (P1) — accepted, disclosed

Correct reading: one k3s server that is also the only PostgreSQL host (`values-demo.yaml`
pins the StatefulSet to it), one agent, `replicas: 1` in the template, one server resource in
the `hcloud` module. ADR-028 accepted this on cost grounds and said "a node loss is a demo
outage"; ADR-035's devil's-advocate paragraph repeats it. What neither did is say what the
brief's "high availability" then means for this delivery, and the final report resolved that
ambiguity in the wrong direction ("we built exactly that", "high availability here means the
data survives and the pipeline recovers"). The reviewer's second closure option is taken:
**the availability boundary is written down** — ADR-028 amendment 1 (Phase 13 task 13.7)
states that the demo is a *recoverable single-primary* deployment: durable capture in two
failure domains, physical and Bronze-only recovery drilled, and **no automatic failover** of the
database or the control plane; the loss of the server is an outage ended by the restore
procedure, whose only measured parts are the warm phases (`docs/07` §5.3). A-6's "recovery has
no manual step" is reconciled to what it is true of: the data path (reconcile, backfill,
replay, invalidation), not node loss on the demo. The production path — three k3s servers with
embedded etcd and CNPG with replicas — is a values and Terraform change that is not exercised,
and the README and the final report say so. Whether to fund and run a failover demonstration is
the author's decision and stays the one open acceptance item of this round.

### R2 — successful captures are classified as missing because the scheduled time is the start time (P2) — accepted, live on the demo

Reproduced on both backends. The cause is exactly as read: `capture --live` without
`--scheduled-for` uses `datetime.now(UTC)`, the CronJob template passes no instant, and the gap
detector (ADR-031) indexes Bronze entries and runs by exact cron instants. The live evidence
says more than the reviewer claims for it: the hourly backfill (limit 8) covers the four
15-minute ticks of each hour, so on the demo **every scheduled capture has been fetched a
second time by the backfill since 2026-09-23** — a phantom `missing_capture` per tick, a second
Bronze entry per tick and twice the source reads the manifests declare. No value is wrong (the
second capture is the same day's file, minutes later) and nothing was lost, but the politeness
argument of ADR-024 §5 and the ledger's diagnostics were both false on the demo. Phase 13 task
13.2: the run's identity is the **schedule's instant** — the CronJob controller's own tick,
read from the Job name the downward API passes (a Job created by a CronJob is named
`<cronjob>-<minutes since the epoch>` of its scheduled time; the demo's
`…-capture-ceps-load-29838195` is 2026-09-24T23:15Z), checked against the manifest's cadence,
with the newest firing instant at or before *now* as the fallback for a manual Job or a laptop
run. A tick no capture served is still missing: the fallback never invents an older instant.
ADR-031 amendment 1; the probe inverted as the negative test, plus the Job-name decode, the
non-firing name, the missed tick, a DST day and a non-UTC cadence.

### R3 — alert definitions are present, but operational alert delivery is not demonstrated (P1) — accepted

Correct reading of the render and the live inventory: `metrics.operator.enabled=false` on the
demo, no Prometheus, no Alertmanager, no kube-state-metrics in any namespace, and five of the
twelve rules read `kube_*` metrics that nothing exports. The rules ConfigMap has shipped "for
any scraper" since ADR-037 and no profile ran one; the final report's "three alert rules watch"
described text, not a process. Phase 13 tasks 13.5 and 13.6 (ADR-040): the chart gains
`alerting.enabled` — Prometheus loading the existing rules ConfigMap unchanged and scraping the
exporter and a **namespaced** kube-state-metrics (a Role, no ClusterRole, no CRD), Alertmanager
routing to a **receiver on the platform image** (`energyctl alert-sink`, one JSON line per
delivery) and to whatever receivers the operator adds by values (SMTP, a webhook), Grafana with
the Prometheus datasource so the existing `freshness.json` dashboard works. On in `local`, the
demo and the all-flags render; off in the tenant default, which stays cluster-rights-free. The
delivery drill the reviewer asks for is `make alert-drill` on kind: a Job named like the restore
drill that exits 1 → `EnergyPlatformRestoreDrillFailed` delivered `firing` at the sink → the
Job deleted → `resolved` delivered; the transcript goes into `docs/07` §7.2, and the same steps
are handed to the author for the demo (Level 3). The core chart still needs no CRD.

### R4 — core-code corrections can replay as no-ops because the release identity stays constant (P1) — accepted, design gap

Reproduced on both backends, and the reading of ADR-023 §1 is right: the derivation identity
names `platform_version`, the package version is `0.0.1` since the skeleton commit, and no
release step changes it; a fix in parser or mapping code that leaves the manifest alone
therefore upserts under the old key and inserts nothing. ADR-023's own consequences paragraph
assumed the opposite ("every platform release changes `derivation_id` for every target") — a
hypothesis the implementation never made true. Phase 13 task 13.3, ADR-023 amendment 3: the
identity carries the **implementation** — `energy_platform.implementation_version()` is the
package version plus a digest over every `.py` file of the package, computed once per process;
it replaces the bare version in `derivation_for` and in the generic `parser_ref`. A code change
is a new derivation, the same code is the same derivation on a laptop and in the image (the
image copies the same files), and an exact retry stays a no-op. One honest note on the
reviewer's probe: it simulates the correction by patching `map_payload` in memory, which cannot
change a file's bytes, so **the probe will keep reporting the defect after the fix by
construction**; the negative tests change bytes instead (a copy of the package with one byte
altered gets another digest, an unchanged copy the same one) and drive the replay through a
patched digest to show the corrected value inserted under a new derivation.

### R5 — fresh restore checks compare shared datasets before all contributing targets are rebuilt (P2) — accepted

Reproduced on both backends: 288 scratch versions against 9 204 live ones when the daily target
is compared first, "ahead by 288" for the monthly target afterwards, a pass on the second run.
`silver_fingerprints` and `_live_side` select by dataset and transport, which three committed
targets share, and `restore_drill` compares each target right after its own rebuild. The saved
live drill's monthly and final rows (576 versions, zero captures) are that defect showing in
production reports, as the challenge reviewer says. Phase 13 task 13.4: the drill **rebuilds
every target before it compares any**, and the comparison is scoped to the target's own lineage
(the rows its attempts produced), with a fingerprint the rebuild attributes to a sibling target
counted as reproduced rather than missing. The reviewer's daily+monthly fixtures on an empty
scratch, on both stores, are the negative test.

### R6 — raw-only rebuilding cannot reproduce historical mapping derivations (P2) — accepted, design

Reproduced on both backends: `ignore_fields` gains an unused name, the derivation changes as
designed, live holds 384 versions across two derivations, the current-manifest rebuild
produces 192 and the drill reports the other 192 missing. The reviewer's distinction from R4 is
exact: giving a change a new identity does not preserve the executable history of the old one,
and no replica holds old code. The guarantee was never stated precisely enough to be wrong —
ADR-036 §5 says "an order-independent checksum over (observation identity, value)", the
implementation compared every version with its derivation id. Phase 13 task 13.4, ADR-036
amendment 5, takes the reviewer's second option: **the Bronze-only rebuild guarantees values.**
Per (observation identity, payload) live holds within the replica bound, the rebuild must
reproduce the value of live's *newest* derivation for that pair; a pair the rebuild lacks is
`missing` (loss), a pair whose value differs is `diverging` (the running code no longer produces
live's value from that payload — an un-replayed correction or a regression; the drill fails and
names it), and versions under retired derivations are `historical` (counted, named, not
compared: the physical backup keeps them, and the drill's first phase proves that backup).
Tested both ways the reviewer asks: the harmless manifest revision passes with 192 historical
versions; a value-changing implementation without a replay is `diverging` and fails, and passes
after the replay.

## Verdicts — the final-report assessment (`02-final-report-assessment.md`)

Every row is accepted and applied in Phase 13 task 13.7 to `docs/overview/final-report.md`,
after the fixes, with these dispositions:

- **HA fulfilment (lines 9, 50–58)** — rewritten to the boundary of R1: a live, recoverable
  single-primary demonstration; interruption and operator recovery stated separately from
  durability.
- **"Proves every night" (9, 31, 57)** — one configured nightly drill; one recorded successful
  manual two-phase run (2026-09-24, 777 s and 1 216 s); the scheduled run before it failed;
  the comparison rule stated as it is after R5/R6.
- **"At most 15 minutes" (55–56)** — the RPO is the replication interval plus copy time under
  successful jobs and an available provider, as ADR-036 amendment 2 and `values-demo.yaml`
  already say; no provider-loss experiment was run.
- **"A bad deploy → nothing" (58)** — bounded to what the hook chain and the drills show: a
  failed upgrade gate rolls the release back; a completed migration and data written by a bad
  release are not undone by Helm (ADR-016 §3–§4, ADR-025 §4); the repair is invalidation or
  replay, or a restore.
- **"Rules actively watch" (100)** — after R3: an evaluator, its metric source and a receiver
  exist in the chart and are exercised on kind; on the demo once the author has pushed the
  values and run the delivery drill there.
- **Four unseen agents / two empty-memory runs (11, 169, 205)** — as `docs/09` records: three
  adapter-path runs and one admission request, one run CLI-only, runs 1–3 with global memory
  present, run 4 the strict empty profile.
- **"Impossible to express" and universal authority (11, 175–177, 199)** — 71 named
  constraints across static, runtime, deployment and procedural gates; branch protection with
  12 required checks and one code-owner review, administrator enforcement off; the sandbox is
  the mechanical boundary and developer-mode sessions hold the owner's authority
  (`docs/threat-model.md` §13).
- **Seven datasets every 15 minutes (9, 46)** — the cadence table stands; the opening and the
  flow paragraph name the three 15-minute targets, the daily, the hourly and the two monthly
  ones, and which have live captured data.
- **"Nothing created by hand" (62–66)** — accounts, credentials, repository variables, the
  namespace Secret and the Terraform state are the documented owner setup.
- **"17 of 17 fixed and closed" (207, 216)** — addressed by their stated dispositions: fixes
  with negative tests, explicit limitations (topology), and deferred capabilities that now
  refuse at render (CNPG/external drill).

The proposed replacement conclusion is adopted in substance and updated for what Phase 13
closes.

## Points from the challenge reports the main review folded in — accepted as stated

- The 29 exact-minute missing captures in the live gap sample are the mechanism of R2, not 29
  independently proven false gaps; the response above claims only what the ledger and the
  backfill limit imply.
- The successful live drill predates the 113 invalidations of 2026-09-24 20:48–21:18 UTC and
  compares under the replica bound; it is evidence for the state it exercised.
- MCP does not open remote PRs (`open_pr` writes a bundle); custom parsers are refused pending a
  loader; the LLM backend is a stub. All three stay in the README's "deliberately not built"
  table and the final report now says them the same way.

## Not changed, and why

- `docs/00`, `01`, `02` are untouched (frozen); ADR-023, ADR-028, ADR-031 and ADR-036 are
  amended with dated entries and `02` keeps its dated pointers.
- The demo's topology is unchanged (R1): the boundary is stated, the failover demonstration is
  the author's decision.
- The live database and the cluster were not touched. The demo receives R2–R6 and the alerting
  values with the author's next push; the delivery drill on the demo and the wiring of a real
  receiver (SMTP or a webhook, by values) are the author's.
- `codex-review/` is verbatim, including the archive the reviewer made.
