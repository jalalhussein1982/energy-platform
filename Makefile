# energy-platform — all logic lives here. CI workflow files only call these targets (ADR-015).
# Conventions: a target that checks something that does not exist yet says so and exits 0;
# a target that needs a tool that is missing while the thing exists FAILS (exit 1). Never fake a pass.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV        ?= uv
UV_VERSION ?= 0.11.7   # pinned installer version for ci-bootstrap (F11); bump deliberately
RUN       := $(UV) run
CHART_DIR := deployment/helm/energy-platform
TF_DIR    := deployment/own-cluster/terraform
KIND_NAME := energy-platform

.PHONY: help check lint lock-check format type test db-test schema deps-allowlist secret-scan helm-lint terraform-validate \
        ci-bootstrap sync local-up local-down smoke-test demo new-target

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-20s %s\n",$$1,$$2}'

# ---------------------------------------------------------------- core gates
check: lint lock-check type test ## lint + lock-check + type + test — must be green before every commit (03 §0)

sync: ## Create/refresh the locked virtualenv (dev group included)
	$(UV) sync --frozen --group dev

lint: sync ## ruff (rules incl. egress ban, naive datetime, swallowed except) + format check + import-linter + target surface (ADR-027)
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) lint-imports
	$(RUN) python scripts/check_target_surface.py targets

lock-check: ## uv.lock must be consistent with pyproject.toml; --frozen alone does not check this (F11)
	$(UV) lock --check

format: sync ## Apply ruff formatting and safe fixes
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

type: sync ## mypy --strict
	$(RUN) mypy

test: sync ## pytest (unit only; live tests are never selected here — ADR-010; db tests skip without a DSN)
	$(RUN) pytest -m "not live"

db-test: sync ## Store suite + migration up/down round trip on an ephemeral local PostgreSQL (ADR-016 §3, ADR-030)
	scripts/with_postgres.sh $(RUN) pytest -m "db" -p no:cacheprovider

schema: sync ## Export schemas/manifest.v1.json from the Pydantic model (ADR-017); a test fails when it is stale
	$(RUN) python -m scripts.export_manifest_schema > schemas/manifest.v1.json

# ---------------------------------------------------------------- supply chain and secrets
deps-allowlist: sync ## Every package in uv.lock must be listed in deps-allowlist.txt (ADR-006/ADR-019)
	$(RUN) python scripts/check_deps_allowlist.py uv.lock deps-allowlist.txt

secret-scan: sync ## Fail on credential-looking strings in tracked files
	$(RUN) python scripts/secret_scan.py

# ---------------------------------------------------------------- deployment gates (real from Phase 5)
helm-lint: ## helm lint + render with tenant values + restricted-PSS check (A-14). Skips honestly until the chart exists.
	@if [ ! -d "$(CHART_DIR)" ]; then \
	  echo "helm-lint: no chart at $(CHART_DIR) yet (Phase 5) — nothing to check"; \
	elif ! command -v helm >/dev/null; then \
	  echo "helm-lint: chart exists but helm is not installed"; exit 1; \
	else \
	  helm lint $(CHART_DIR) -f deployment/tenant/values-tenant.yaml && \
	  helm template ep $(CHART_DIR) -f deployment/tenant/values-tenant.yaml > /tmp/ep-rendered.yaml && \
	  $(RUN) python scripts/check_restricted_pss.py /tmp/ep-rendered.yaml; \
	fi

terraform-validate: ## terraform fmt/validate/test with mock providers. Skips honestly until the profile exists.
	@if [ ! -d "$(TF_DIR)" ]; then \
	  echo "terraform-validate: no Terraform at $(TF_DIR) yet (Phase 5) — nothing to check"; \
	elif ! command -v terraform >/dev/null; then \
	  echo "terraform-validate: Terraform exists but terraform is not installed"; exit 1; \
	else \
	  terraform -chdir=$(TF_DIR) fmt -check -recursive && \
	  terraform -chdir=$(TF_DIR) init -backend=false -input=false && \
	  terraform -chdir=$(TF_DIR) validate && \
	  terraform -chdir=$(TF_DIR) test; \
	fi

ci-bootstrap: ## Install uv on a bare CI runner (the only tool installation CI is allowed to do)
	@command -v $(UV) >/dev/null && { echo "uv present: $$($(UV) --version)"; exit 0; } || true
	curl -LsSf https://astral.sh/uv/$(UV_VERSION)/install.sh | sh
	@echo 'add $$HOME/.local/bin to PATH in the workflow step if not already'

# ---------------------------------------------------------------- local reproduction (ADR-010) — Phase 5
local-up: ## kind cluster → Helm deps → platform → migrations → smoke tests
	@echo "local-up: not implemented until Phase 5 (deployment/local/)"; exit 1

local-down: ## Tear the kind cluster down
	@echo "local-down: not implemented until Phase 5"; exit 1

smoke-test: ## One capture+process on a fixture target, freshness metric present, restore-drill dry-run
	@echo "smoke-test: not implemented until Phase 5"; exit 1

demo: ## fixture → capture → Bronze → parse → map → Postgres → query, offline
	@echo "demo: not implemented until Phase 2 (energyctl demo)"; exit 1

new-target: ## energyctl new-target <id> --modality <m>
	@echo "new-target: not implemented until Phase 3 (energyctl new-target)"; exit 1
