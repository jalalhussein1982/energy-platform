# energy-platform runtime image (Phase 5 plan P5-D2; ADR-016 §1 images by digest).
#
# One image for every workload the chart runs: capture / process / recapture / gaps+freshness
# CronJobs, the migrate / storage-probe / smoke hook Jobs, the restore drill. The entrypoint is
# `energyctl` (python -m energy_platform.cli); the chart passes the verb and its flags as args.
# The committed targets (manifests + fixtures) travel inside the image so a release is one
# immutable bundle: chart version + image digest + target manifests (ADR-016 §1).
#
# No shell is needed by any verb, but /bin/sh stays: Kubernetes exec for an operator is a
# legitimate need on a platform image (the MCP sandbox image is the one that removes it).
# Runs as uid 10001; the root filesystem is read-only in the chart, /tmp is an emptyDir.

FROM ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a AS uv

FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_FROZEN=1 \
    UV_NO_CACHE=1 \
    ENERGY_PLATFORM_TARGETS=/app/targets

# libpq5: psycopg's pure-Python implementation links the system libpq at import time (ADR-030).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md /app/
RUN uv sync --frozen --no-dev --no-install-project \
 && groupadd --gid 10001 platform \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin platform \
 && rm -f /usr/local/bin/uv
COPY energy_platform /app/energy_platform
COPY targets /app/targets

USER 10001:10001
ENTRYPOINT ["/app/.venv/bin/python", "-m", "energy_platform.cli"]
CMD ["--help"]
