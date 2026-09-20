# Sandbox: constrained-agent mode (ADR-007)

In developer mode the MCP server is a convenience and **CI is the enforcement**. In
constrained-agent mode the agent runs inside this container and the container is the
**boundary** (ADR-027 §5): repository mutation happens only through the eight tools of
`energy_platform.mcp`, and the process cannot reach anything the operator did not attach.

## What the container deliberately lacks

| Removed / absent | Why |
|---|---|
| `/bin/sh`, `bash`, `dash` | no shell for `docker exec`, no shell for the agent client to spawn (05 C-47) |
| `kubectl`, `terraform`, cloud CLIs, `git` | Level 3 actions are impossible, not merely forbidden (ADR-006) |
| `uv` after the build, `pip` usable only by root | no dependency can be added at run time (05 C-38) |
| secrets, kubeconfig, `.env` | `read_repository` denies them anyway (05 C-52); here they do not exist |
| pytest (dev group) | `run_target_tests` still runs every golden through the platform pipeline |
| root | `USER agent` (uid 10001); `/workspace` and `/outbox` are the only writable mounts |

## Run

```sh
docker build -f deployment/sandbox/Dockerfile -t energy-platform-sandbox .
docker network create --internal sandbox-net        # no route anywhere (fixtures from files)

docker run --rm -i \
  --network sandbox-net \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 1g --cpus 1 \
  -v "$PWD/checkout:/workspace" -v "$PWD/outbox:/outbox" \
  energy-platform-sandbox
```

The agent client (Claude Code, an MCP-capable IDE, a custom loop) talks JSON-RPC 2.0 on the
container's stdin/stdout. `/workspace` is a checkout of this repository **without `.git`**
(`git archive` or a sparse copy): the agent reads docs and examples and writes only under
`targets/<id>/`. `/outbox` receives the bundle `open_pr` produces.

## Egress

`--network sandbox-net` with `--internal` gives the process no route at all. That is the default
because every tool works offline (`record_fixture` from a saved payload, goldens through the
platform pipeline). Two narrower escapes exist, both explicit:

| Need | How | Note |
|---|---|---|
| Record a live fixture | a network whose only allowed destinations are the registered source hosts on 443 (e.g. a user-defined bridge with `iptables` `OUTPUT` rules, or a policy-enforcing CNI in Kubernetes), **and** `--allow-network` appended to the `docker run` command | the fetch layer still enforces ADR-026 layer 2 (host registry, private-range rejection, redirects) inside |
| Push the PR | **not from inside**. A sidecar or a human runs `python -m scripts.apply_pr_bundle /outbox/<bundle>.json --repo <checkout>` and `gh pr create --base main --head target/<id>` | the bundle is verified (paths confined to one target, hashes) before anything is written; `main` is never touched (05 C-53) |

The Git remote is therefore reached by the sidecar's credentials, never by the agent's process.
Branch protection (`docs/branch-protection.md`) and CODEOWNERS decide what merges.

## In Kubernetes

The same image runs as a `Job` with `automountServiceAccountToken: false`, the restricted Pod
Security profile, requests/limits (A-8) and an egress `NetworkPolicy` that allows nothing (or the
source hosts' `ipBlock`s on 443 for a live-fixture session). The chart is Phase 5 work; the
container contract above does not change.

## What this does not claim

The sandbox constrains the agent's *process*. Prompt injection through a hostile source document
is handled upstream by the triage design of ADR-008 (bounded extraction, LLM output limited to a
PR) and downstream by the gates: whatever an agent writes still passes `make check` and a human
before it runs in production.
