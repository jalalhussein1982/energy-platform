# Constrained-agent sandbox (ADR-007 mode 2; docs/05-constraint-matrix.md §3).
#
# The agent inside this container has ONE interface: the MCP server on stdin/stdout. There is no
# shell binary left to exec into, no kubectl, no terraform, no cloud CLI, no secrets, and the
# container runs unprivileged. Egress is not decided here but by the network the operator attaches
# (README.md): the Git remote only, or nothing at all when fixtures come from files.
#
# Images by digest (ADR-016 §1): both FROM lines are pinned; `make workload-check` refuses a tag.

FROM ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a AS uv

FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_FROZEN=1 \
    UV_NO_CACHE=1

# The platform library, locked. No dev group: pytest is not in the image, so `run_target_tests`
# reports the goldens (the platform pipeline) and says that pytest is unavailable.
# libpq5: energyctl imports psycopg at start-up even for mcp-serve (found in Phase 5, P5-D2).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md /app/
COPY energy_platform /app/energy_platform
RUN uv sync --frozen --no-dev --no-install-project \
 && groupadd --gid 10001 agent \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin agent \
 && mkdir -p /workspace /outbox \
 && chown -R agent:agent /workspace /outbox \
 && rm -f /usr/local/bin/uv \
 && rm -f /bin/sh /bin/bash /bin/dash /usr/bin/sh /usr/bin/bash /usr/bin/dash

USER agent:agent
VOLUME ["/workspace", "/outbox"]

# `energyctl mcp-serve`: JSON-RPC 2.0 over stdio, tools = the ADR-007 eight, nothing else.
# `--allow-network` is deliberately NOT here; add it on the command line only for a session that
# records live fixtures on a network that reaches the source hosts and nothing else.
ENTRYPOINT ["/app/.venv/bin/python", "-m", "energy_platform.cli", "mcp-serve", "--root", "/workspace", "--outbox", "/outbox"]
