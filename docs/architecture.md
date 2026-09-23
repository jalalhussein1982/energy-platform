# Architecture

One library (`energy_platform`), thin clients (`energyctl`, the MCP server, CI), one Helm chart,
two Terraform roots (ADR-000, ADR-001). Sources are untrusted data; Bronze is the durable boundary
and Postgres is authoritative for Silver (ADR-002, ADR-024). Contributors own syntax, the platform
owns semantics (ADR-005), and nothing reaches `main` or the cluster without CI and a human
(ADR-006). The diagrams below are the demo environment (ADR-028); the security reading of each
arrow is `docs/threat-model.md`.

## 1. Data path

```mermaid
flowchart LR
  subgraph SRC["Public sources: untrusted data"]
    direction TB
    OTESOAP["OTE SOAP<br/>PublicDataService"]
    OTEXLSX["OTE daily XLSX<br/>discovery page + file"]
    CEPS["ČEPS SOAP<br/>load"]
  end

  subgraph NS["k3s namespace energy-platform: CronJob + run ledger, restricted PSS"]
    FETCH["energy_platform.fetch<br/>host registry, https only,<br/>private-range and peer checks,<br/>every redirect hop validated"]
    CAP["capture<br/>fetch, write raw, then ack"]
    PROC["process<br/>reconcile, claim with fence"]
    PARSE["parse<br/>generic decoders, XXE off"]
    MAP["mapping<br/>registry contracts:<br/>unit, sign rule, NULL meaning"]
    GAPS["gaps + freshness<br/>missing_capture, unprocessed_capture"]
    EXP["freshness exporter<br/>postgres_exporter :9187"]
    subgraph PG["PostgreSQL, statefulset on the server volume"]
      LEDGER[("run ledger<br/>runs, run_attempts, fence")]
      SILVER[("Silver<br/>bitemporal, tstzrange,<br/>append-only versions")]
      FRESH[("target_freshness")]
    end
    BACKUP["pg-wal-ship + pg-backup<br/>gzip WAL every 10 min, base daily"]
    REPL["replicate<br/>rclone copy --immutable --checksum"]
    DRILL["restore-drill<br/>scratch Postgres, reconcile,<br/>replay, compare with live"]
  end

  A[("Bronze store A<br/>Hetzner Object Storage<br/>Object Lock COMPLIANCE 90 d")]
  B[("Store B<br/>OCI Object Storage Frankfurt<br/>retention rule, versioning off")]
  PROM["metrics<br/>Prometheus annotations, alert rules"]

  OTESOAP & OTEXLSX & CEPS -->|"https, registered hosts"| FETCH
  FETCH --> CAP
  CAP -->|"1: blob by sha256 + capture-log entry"| A
  CAP -->|"2: ledger row, state captured"| LEDGER
  A -->|"capture log + hash-verified blob"| PROC
  LEDGER -->|"claim"| PROC
  PROC --> PARSE --> MAP
  MAP -->|"fenced upsert, derivation_id"| SILVER
  LEDGER & SILVER --> GAPS
  GAPS -->|"backfill or replay rows"| LEDGER
  GAPS --> FRESH --> EXP --> PROM
  SILVER -.->|"WAL + base, whole database"| BACKUP
  BACKUP -->|"backups/postgres/SYSTEM_ID/"| A
  A -->|"whole bucket"| REPL --> B
  B -->|"base, WAL, Bronze"| DRILL
```

- Ordering is `FETCH → WRITE RAW → ACKNOWLEDGE → PROCESS` (ADR-004): the capture needs no
  database, and `reconcile` rebuilds the ledger from the capture log (ADR-024 §1–§2).
- Replay reads Bronze and never fetches; backfill is the only other fetching verb (ADR-024 §5).
- Egress layer 1 (`NetworkPolicy`): only capture and backfill pods reach the internet, on 443,
  private ranges excepted (ADR-026).
- Store B is written only by `replicate`; the drill reads B, never A (ADR-036 §3, §5).
  Archive paths carry the Postgres system identifier (ADR-036 amendment 1 §6).
- Freshness is the SLI; `source_unavailable` and `pipeline_failed` are separate metrics
  (ADR-012, ADR-037).

## 2. Contributor and agent path

```mermaid
flowchart TB
  subgraph WHO["Target author: junior or agent"]
    DEV["developer mode<br/>energyctl + editor;<br/>CI is the enforcement"]
    SBX["constrained-agent mode<br/>sandbox: no shell, no secrets,<br/>no network by default"]
  end

  TOOLS["energyctl or MCP, the ADR-007 eight tools<br/>read_repository, inspect_target, scaffold_target,<br/>write_target_file, validate_target, record_fixture,<br/>run_target_tests, open_pr"]
  TGT["targets/‹id›/ only, ADR-027<br/>manifest.yaml, optional parser.py, README,<br/>fixtures as Bronze objects, golden tests"]
  VAL{"energyctl validate"}
  PRA["Route A pull request<br/>targets/‹id›/ only"]
  ADM["Route B admission request<br/>docs/admissions/‹id›.md, nothing else"]
  CI["CI, 12 required jobs<br/>lint, lock-check, type, test, db-test, demo,<br/>harness-check, pr-surface, deps-allowlist,<br/>secret-scan, helm-lint, terraform-validate"]
  REV["human review<br/>CODEOWNERS"]
  MAIN["main"]
  MAINT["maintainer decides admission"]
  REG["Route B platform PR<br/>registry.py, hosts.py, 01 §10 row, ADR"]

  DEV & SBX --> TOOLS --> TGT --> VAL
  VAL -->|"OK"| PRA
  VAL -->|"ADMISSION_REQUIRED"| ADM
  PRA & ADM --> CI
  ADM -.-> MAINT --> REG --> CI
  CI --> REV -->|"merge"| MAIN

  subgraph TRI["Drift triage, ADR-008 mandatory flow; LLM stubbed, D-10"]
    DRIFT["drifted Bronze capture<br/>quarantine or unknown_field"]
    EXT["bounded extractor<br/>max 3 records, 64 chars per value,<br/>4000 chars, JSON data only"]
    LLM["LLMBackend<br/>HeuristicStubBackend by default"]
    CON["constrain + verify<br/>rename_source, set_decimal_separator,<br/>add_ignore_field; manifest paths only"]
    PROP["proposal file<br/>outbox/triage-‹id›-‹stamp›.json"]
  end

  DRIFT --> EXT --> LLM --> CON --> PROP
  PROP -->|"a human applies it"| PRA
```

- `pr-surface` fails a PR that mixes `targets/<id>/` with anything else or touches two targets;
  registry, allowlist and CI paths are named (05 C-39…C-41).
- In the sandbox, `open_pr` writes a bundle to `/outbox`; `scripts/apply_pr_bundle.py` runs
  outside, re-verifies paths and hashes, and never commits on `main` (05 C-51, C-53).
- Route B is a maintainer decision no gate automates (ADR-022 §1); the registries are
  CODEOWNERS paths.
- Triage never pushes and cannot express a unit, sign, host, URL, licence or cadence change
  (`docs/plans/phase-6.md` P6-D3; 05 C-58…C-61).

## 3. Deployment (demo)

```mermaid
flowchart LR
  subgraph GH["GitHub, public repository"]
    MAINB["main, branch protection"]
    IMG["deploy-demo: image job<br/>packages: write only"]
    DEP["deploy-demo: deploy job<br/>id-token: write only"]
  end
  GHCR[("GHCR package, private<br/>image by digest")]
  TF["Terraform roots/hcloud<br/>network, nodes, storage, security<br/>apply: author, Level 3"]

  subgraph HZ["Hetzner nbg1"]
    SRV["k3s server cx23<br/>API 6443, anonymous off,<br/>OIDC: repository + refs/heads/main"]
    AGT["k3s agent cx23"]
    VOL[("volume 10 GB<br/>Postgres data")]
    ROLE["namespace energy-platform<br/>Role bound to gha:owner/repo"]
    BA[("bucket A<br/>Object Lock COMPLIANCE")]
  end

  subgraph OCI["OCI Frankfurt"]
    BB[("bucket B<br/>retention rule")]
  end

  MAINB -->|"workflow_dispatch"| IMG
  IMG -->|"push with the job token"| GHCR
  IMG -->|"digest"| DEP
  DEP -->|"GitHub OIDC token, audience energy-platform-demo"| SRV
  SRV -->|"RBAC"| ROLE
  GHCR -->|"pull with the ghcr-pull Secret"| ROLE
  TF --> SRV & AGT & VOL & BA & BB
  VOL --- SRV
  ROLE -->|"Bronze, backups"| BA
  BA -->|"replicate"| BB
```

- No kubeconfig or token is stored in CI; the admin client certificate stays with the author
  outside the repository (ADR-015, ADR-035 §2, V-14).
- 6443 is open to the internet because GitHub-hosted runner ranges do not fit the firewall;
  authentication and the namespace `Role` are the controls (ADR-035 §4).
- The same chart and `tenant` values deploy here; nothing needs cluster rights (ADR-028 §2).
