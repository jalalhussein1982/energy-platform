# energy-platform — all logic lives here. CI workflow files only call these targets (ADR-015).
# Conventions: a target that checks something that does not exist yet says so and exits 0;
# a target that needs a tool that is missing while the thing exists FAILS (exit 1). Never fake a pass.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV        ?= uv
# uv for ci-bootstrap (F11): a pinned release asset, checked against its SHA-256 (the release's
# uv-x86_64-unknown-linux-gnu.tar.gz.sha256, re-checked on the download). Bump both together.
# No comment after a value: Make keeps the spaces before a trailing `#` and the URL would break.
UV_VERSION ?= 0.11.7
UV_SHA256  ?= 6681d691eb7f9c00ac6a3af54252f7ab29ae72f0c8f95bdc7f9d1401c23ea868
RUN       := $(UV) run
CHART_DIR := deployment/helm/energy-platform
TF_DIR    := deployment/own-cluster/terraform
KIND_NAME := energy-platform
DOCKER    ?= docker
IMAGE_REPO ?= energy-platform
IMAGE_TAG  ?= dev
IMAGE      := $(IMAGE_REPO):$(IMAGE_TAG)
IMAGE_PLATFORM ?=                        # e.g. linux/amd64 for the demo's cx23 nodes; empty = the build host's
IMAGE_DIGEST   ?=                        # sha256:… of a pushed image; deploy-tenant reads the local Docker when empty

.PHONY: help check lint lock-check format type test db-test schema fixtures deps-allowlist secret-scan helm-lint terraform-validate \
        ci-bootstrap sync local-up local-down smoke-test demo new-target validate-targets migration-check workload-check \
        harness-check pr-surface live-smoke image image-push image-digest target-values \
        local-cluster local-registry local-cni local-image local-secrets deploy-local local-egress-test terraform-plan-hcloud \
        deploy-tenant kubeconfig-oidc deploy-demo print-demo-secret-template rollback-drill ci-kind-tools ci-terraform \
        demo-reconfigure helm-driver-migrate

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-20s %s\n",$$1,$$2}'

# ---------------------------------------------------------------- core gates
check: lint lock-check type test harness-check ## lint + lock-check + type + test + harness-check — green before every commit (03 §0)

sync: ## Create/refresh the locked virtualenv (dev group included)
	$(UV) sync --frozen --group dev

lint: sync ## ruff (rules incl. egress ban, naive datetime, swallowed except) + format check + import-linter + target surface (ADR-027)
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) lint-imports
	$(RUN) python -m scripts.check_target_surface targets

lock-check: ## uv.lock must be consistent with pyproject.toml; --frozen alone does not check this (F11)
	$(UV) lock --check

format: sync ## Apply ruff formatting and safe fixes
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

type: sync ## mypy --strict
	$(RUN) mypy

test: sync ## pytest (unit only; live tests are never selected here — ADR-010; db tests skip without a DSN)
	$(RUN) pytest -m "not live"

live-smoke: sync ## Nightly: one bounded live read per committed target, shape only; never in PR CI (ADR-020, P4-D10)
	$(RUN) pytest -m live tests/live

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
HELM ?= helm
# Helm 4 renamed --atomic to --rollback-on-failure and made --wait hook-only by default; the
# deploy targets need the same semantics ADR-025 names (--atomic --wait) on either major.
HELM_MAJOR := $(shell $(HELM) version --short 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
HELM_ATOMIC := $(if $(filter 4,$(HELM_MAJOR)),--rollback-on-failure --wait=watcher --wait-for-jobs,--atomic --wait --wait-for-jobs)
HELM_TIMEOUT ?= 15m
LINT_DIGEST := sha256:0000000000000000000000000000000000000000000000000000000000000000
TARGET_VALUES := /tmp/ep-targets.yaml

target-values: sync ## Render the chart's targets: values from targets/*/manifest.yaml (P5-D3; refuses a restricted licence)
	$(RUN) python -m scripts.render_target_values targets > $(TARGET_VALUES)

helm-lint: sync ## helm lint + template (tenant, local, all-flags) → workload digests/resources + restricted-PSS check (A-14). Skips honestly until the chart exists.
	@if [ ! -d "$(CHART_DIR)" ]; then \
	  echo "helm-lint: no chart at $(CHART_DIR) yet (Phase 5) — nothing to check"; \
	elif ! command -v $(HELM) >/dev/null; then \
	  echo "helm-lint: chart exists but helm is not installed"; exit 1; \
	else \
	  $(RUN) python -m scripts.render_target_values targets > $(TARGET_VALUES) && \
	  for values in deployment/tenant/values-tenant.yaml deployment/local/values-local.yaml $(CHART_DIR)/ci/all-flags-values.yaml; do \
	    echo "== helm-lint: $$values"; \
	    $(HELM) lint $(CHART_DIR) -f $$values -f $(TARGET_VALUES) --set image.digest=$(LINT_DIGEST) && \
	    $(HELM) template ep $(CHART_DIR) -f $$values -f $(TARGET_VALUES) --set image.digest=$(LINT_DIGEST) > /tmp/ep-rendered.yaml && \
	    $(RUN) python -m scripts.check_workloads /tmp/ep-rendered.yaml && \
	    $(RUN) python -m scripts.check_restricted_pss /tmp/ep-rendered.yaml || exit 1; \
	  done; \
	fi

TF ?= $(shell command -v terraform 2>/dev/null || command -v tofu 2>/dev/null)
TF_ROOTS := $(wildcard $(TF_DIR)/roots/*)
TF_PLAN_DIR ?= $(HOME)/.config/energy-platform/plans

terraform-validate: ## fmt -check, init -backend=false, validate, test (mock providers) for every root; terraform or tofu. Skips honestly until the profile exists.
	@if [ ! -d "$(TF_DIR)" ]; then \
	  echo "terraform-validate: no Terraform at $(TF_DIR) yet (Phase 5) — nothing to check"; \
	elif [ -z "$(TF)" ]; then \
	  echo "terraform-validate: Terraform exists but neither terraform nor tofu is installed"; exit 1; \
	else \
	  $(TF) fmt -check -recursive $(TF_DIR) && \
	  for root in $(TF_ROOTS); do \
	    echo "== terraform-validate: $$root ($(notdir $(TF)))"; \
	    $(TF) -chdir=$$root init -backend=false -input=false >/dev/null && \
	    $(TF) -chdir=$$root validate && \
	    $(TF) -chdir=$$root test || exit 1; \
	  done; \
	fi

terraform-plan-hcloud: ## Plan the demo root into $(TF_PLAN_DIR) (outside the repository); never applies (Level 3)
	@test -n "$(TF)" || { echo "terraform-plan-hcloud: neither terraform nor tofu installed"; exit 1; }
	@mkdir -p $(TF_PLAN_DIR)
	$(TF) -chdir=$(TF_DIR)/roots/hcloud init -backend=false -input=false >/dev/null
	$(TF) -chdir=$(TF_DIR)/roots/hcloud plan -input=false -out=$(TF_PLAN_DIR)/hcloud-$$(date +%Y%m%d-%H%M%S).tfplan
	@echo "terraform-plan-hcloud: plan written under $(TF_PLAN_DIR); apply is the author's (Level 3)"

ci-bootstrap: ## Install uv $(UV_VERSION) on a bare CI runner (linux x86_64, SHA-256 checked; the only tool installation CI is allowed to do)
	@# one shell: `exit 0` on a separate recipe line would not skip the install
	@if command -v $(UV) >/dev/null; then echo "uv present: $$($(UV) --version)"; exit 0; fi; \
	curl -fsSLo /tmp/uv.tar.gz https://github.com/astral-sh/uv/releases/download/$(UV_VERSION)/uv-x86_64-unknown-linux-gnu.tar.gz \
	  && echo "$(UV_SHA256)  /tmp/uv.tar.gz" | sha256sum -c - \
	  && mkdir -p "$$HOME/.local/bin" \
	  && tar -xzf /tmp/uv.tar.gz -C "$$HOME/.local/bin" --strip-components=1 uv-x86_64-unknown-linux-gnu/uv uv-x86_64-unknown-linux-gnu/uvx \
	  || { echo "ci-bootstrap: uv $(UV_VERSION) download or checksum failed"; exit 1; }; \
	"$$HOME/.local/bin/uv" --version; \
	if [ -n "$${GITHUB_PATH:-}" ]; then echo "$$HOME/.local/bin" >> "$$GITHUB_PATH"; echo "ci-bootstrap: $$HOME/.local/bin added to PATH for the next steps"; \
	else echo 'ci-bootstrap: add $$HOME/.local/bin to PATH if it is not there'; fi

# ---------------------------------------------------------------- platform image (ADR-016 §1, P5-D2)
image: ## Build the platform runtime image deployment/image/Dockerfile as $(IMAGE) (for IMAGE_PLATFORM when set)
	$(DOCKER) build $(if $(IMAGE_PLATFORM),--platform $(IMAGE_PLATFORM)) -f deployment/image/Dockerfile -t $(IMAGE) .

image-push: image ## Build and push $(IMAGE); logs in with REGISTRY_USER/REGISTRY_TOKEN when set (CI: the job token); prints the digest and, in CI, writes it to GITHUB_OUTPUT (plan P5-D20)
	@if [ -n "$${REGISTRY_TOKEN:-}" ]; then \
	  printf '%s' "$$REGISTRY_TOKEN" | $(DOCKER) login $(firstword $(subst /, ,$(IMAGE_REPO))) -u "$${REGISTRY_USER:?REGISTRY_USER unset}" --password-stdin; \
	fi
	$(DOCKER) push $(IMAGE)
	@ref="$$(make -s image-digest)" && test -n "$$ref" || { echo "image-push: no digest for $(IMAGE) after the push" >&2; exit 1; }; \
	echo "image-push: $$ref"; \
	if [ -n "$${GITHUB_OUTPUT:-}" ]; then echo "digest=$${ref##*@}" >> "$$GITHUB_OUTPUT"; fi

LOCAL_REGISTRY      ?= kind-registry
LOCAL_REGISTRY_PORT ?= 5001
LOCAL_IMAGE_REPO    := localhost:$(LOCAL_REGISTRY_PORT)/$(IMAGE_REPO)
# registry:2, resolved 2026-09-22
REGISTRY_IMAGE      ?= docker.io/library/registry:2@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373

image-digest: ## Print the digest reference of $(IMAGE): from the kind-attached registry (FROM_LOCAL_REGISTRY=1, after make local-image) or from RepoDigests (after a push)
	@if [ -n "$(FROM_LOCAL_REGISTRY)" ]; then \
	  ref="$$($(DOCKER) image inspect --format '{{range .RepoDigests}}{{.}}{{"\n"}}{{end}}' $(LOCAL_IMAGE_REPO):$(IMAGE_TAG) 2>/dev/null | grep '^$(LOCAL_IMAGE_REPO)@sha256:' | head -1)"; \
	  test -n "$$ref" || { echo "image-digest: $(LOCAL_IMAGE_REPO):$(IMAGE_TAG) has no digest; run make local-image" >&2; exit 1; }; \
	  echo "$$ref"; \
	else \
	  ref="$$($(DOCKER) image inspect --format '{{range .RepoDigests}}{{.}}{{"\n"}}{{end}}' $(IMAGE) 2>/dev/null | grep '^$(IMAGE_REPO)@sha256:' | head -1)"; \
	  test -n "$$ref" || { echo "image-digest: $(IMAGE) has no RepoDigest; push it to a registry first (or FROM_LOCAL_REGISTRY=1 after make local-image)" >&2; exit 1; }; \
	  echo "$$ref"; \
	fi

# ---------------------------------------------------------------- local reproduction (ADR-010) — Phase 5
KUBECTL       ?= kubectl
KIND          ?= kind
NAMESPACE     ?= energy-platform
RELEASE       ?= energy-platform
CILIUM_VERSION ?= 1.20.2
KIND_CONTEXT  := kind-$(KIND_NAME)
KUBE          := $(KUBECTL) --context $(KIND_CONTEXT)
HELM_KIND     := $(HELM) --kube-context $(KIND_CONTEXT)

local-up: image local-cluster local-registry local-cni local-image local-secrets deploy-local local-egress-test ## kind + registry + Cilium → image by digest → secrets → atomic deploy (hooks: migrate, smoke) → layer-1 egress test
	@echo "local-up: done — kubectl --context $(KIND_CONTEXT) -n $(NAMESPACE) get cronjobs,jobs,pods"

local-cluster: ## Create the kind cluster from deployment/local/kind-config.yaml (idempotent)
	@if $(KIND) get clusters 2>/dev/null | grep -qx $(KIND_NAME); then echo "local-cluster: $(KIND_NAME) exists"; \
	else $(KIND) create cluster --config deployment/local/kind-config.yaml; fi   # no --wait: the node is Ready only after Cilium

local-cni: ## Cilium with policy enforcement (kindnet does not enforce NetworkPolicy, ADR-026 §4)
	$(HELM) repo add cilium https://helm.cilium.io/ >/dev/null 2>&1 || true
	$(HELM) repo update cilium >/dev/null
	$(HELM_KIND) upgrade --install cilium cilium/cilium --version $(CILIUM_VERSION) -n kube-system \
	  -f deployment/local/cilium-values.yaml --wait --timeout 10m
	$(KUBE) -n kube-system rollout status ds/cilium --timeout=300s
	$(KUBE) wait --for=condition=Ready node --all --timeout=180s

local-registry: ## A registry container attached to the kind network; nodes resolve localhost:$(LOCAL_REGISTRY_PORT) to it (kind's local-registry recipe)
	@if [ "$$($(DOCKER) inspect -f '{{.State.Running}}' $(LOCAL_REGISTRY) 2>/dev/null)" != "true" ]; then \
	  $(DOCKER) run -d --restart=always -p "127.0.0.1:$(LOCAL_REGISTRY_PORT):5000" --network bridge --name $(LOCAL_REGISTRY) $(REGISTRY_IMAGE) >/dev/null; fi
	@$(DOCKER) network inspect kind -f '{{range .Containers}}{{.Name}} {{end}}' | grep -qw $(LOCAL_REGISTRY) || $(DOCKER) network connect kind $(LOCAL_REGISTRY)
	@for node in $$($(KIND) get nodes --name $(KIND_NAME)); do \
	  $(DOCKER) exec "$$node" mkdir -p /etc/containerd/certs.d/localhost:$(LOCAL_REGISTRY_PORT); \
	  printf '[host."http://%s:5000"]\n' $(LOCAL_REGISTRY) | $(DOCKER) exec -i "$$node" cp /dev/stdin /etc/containerd/certs.d/localhost:$(LOCAL_REGISTRY_PORT)/hosts.toml; \
	done

local-image: ## Push $(IMAGE) to the kind-attached registry; the deploy references it by the digest the push returns
	$(DOCKER) tag $(IMAGE) $(LOCAL_IMAGE_REPO):$(IMAGE_TAG)
	$(DOCKER) push $(LOCAL_IMAGE_REPO):$(IMAGE_TAG)
	@echo "local-image: $$(make -s image-digest FROM_LOCAL_REGISTRY=1)"

local-secrets: ## Generate the local Secret (random Postgres password and MinIO keys); never asks for credentials (P5-D10)
	@$(KUBE) get namespace $(NAMESPACE) >/dev/null 2>&1 || $(KUBE) create namespace $(NAMESPACE) >/dev/null
	@$(KUBE) -n $(NAMESPACE) get secret $(RELEASE) >/dev/null 2>&1 && echo "local-secrets: $(RELEASE) exists" || \
	$(KUBE) -n $(NAMESPACE) create secret generic $(RELEASE) \
	  --from-literal=POSTGRES_PASSWORD=$$(openssl rand -hex 16) \
	  --from-literal=BRONZE_ACCESS_KEY_ID=minioa$$(openssl rand -hex 6) \
	  --from-literal=BRONZE_SECRET_ACCESS_KEY=$$(openssl rand -hex 20) \
	  --from-literal=BRONZE_REPLICA_ACCESS_KEY_ID=miniob$$(openssl rand -hex 6) \
	  --from-literal=BRONZE_REPLICA_SECRET_ACCESS_KEY=$$(openssl rand -hex 20)

deploy-local: target-values ## helm upgrade --install with rollback-on-failure + wait (hooks gate the release, ADR-025)
	$(HELM_KIND) upgrade --install $(RELEASE) $(CHART_DIR) -n $(NAMESPACE) --create-namespace \
	  -f deployment/local/values-local.yaml -f $(TARGET_VALUES) \
	  --set image.repository=$(LOCAL_IMAGE_REPO) \
	  --set image.digest=$$(make -s image-digest FROM_LOCAL_REGISTRY=1 | sed 's/.*@//') \
	  $(HELM_ATOMIC) --timeout $(HELM_TIMEOUT) $(HELM_EXTRA)

local-egress-test: ## ADR-026 §4: capture pod reaches 443; metadata/private blocked; process pod has no internet
	$(KUBE) -n $(NAMESPACE) delete job -l energy-platform.io/test=egress --ignore-not-found >/dev/null
	$(KUBE) -n $(NAMESPACE) apply -f deployment/local/egress-test-job.yaml >/dev/null
	@fail=0; for j in egress-test-capture-allowed egress-test-capture-blocked egress-test-process-blocked; do \
	  if $(KUBE) -n $(NAMESPACE) wait --for=condition=complete job/$$j --timeout=120s >/dev/null 2>&1; then \
	    echo "PASS $$j: $$($(KUBE) -n $(NAMESPACE) logs job/$$j | tr '\n' ' ')"; \
	  else \
	    if [ "$$j" = egress-test-capture-allowed ] && [ -n "$(LOCAL_EGRESS_OFFLINE)" ]; then echo "SKIP $$j (LOCAL_EGRESS_OFFLINE=1)"; \
	    else echo "FAIL $$j: $$($(KUBE) -n $(NAMESPACE) logs job/$$j 2>/dev/null | tr '\n' ' ')"; fail=1; fi; \
	  fi; \
	done; exit $$fail

# ---------------------------------------------------------------- tenant / demo deploys (ADR-001 amend, ADR-028, ADR-015)
ENV ?= demo
OIDC_KUBECONFIG := /tmp/ep-oidc-kubeconfig
DEMO_SECRET_KEYS := POSTGRES_PASSWORD BRONZE_ACCESS_KEY_ID BRONZE_SECRET_ACCESS_KEY BRONZE_REPLICA_ACCESS_KEY_ID BRONZE_REPLICA_SECRET_ACCESS_KEY
# Store B's endpoint for ENV=demo: the OCI tenancy namespace (`oci os ns get`) stays out of the
# repository and comes from DEMO_OCI_NAMESPACE (a repository variable in CI; plan P5-D22).
DEMO_OCI_NAMESPACE ?=
DEMO_OCI_ENDPOINT = https://$(DEMO_OCI_NAMESPACE).compat.objectstorage.eu-frankfurt-1.oraclecloud.com

# Tenant deploys keep Helm's release records as ConfigMaps: the deploy identity needs no `secrets`
# verbs (ADR-035 amendment 1). Read them the same way: HELM_DRIVER=configmap helm history …
TENANT_HELM_DRIVER ?= configmap

deploy-tenant: target-values ## helm upgrade --install with tenant values + values-$(ENV).yaml (KUBECONFIG = a namespace-scoped kubeconfig); IMAGE_DIGEST, or IMAGE with a RepoDigest
	@test -f deployment/tenant/values-$(ENV).yaml || { echo "deploy-tenant: deployment/tenant/values-$(ENV).yaml does not exist"; exit 1; }
	HELM_DRIVER=$(TENANT_HELM_DRIVER) $(HELM) upgrade --install $(RELEASE) $(CHART_DIR) -n $(NAMESPACE) \
	  -f deployment/tenant/values-tenant.yaml -f deployment/tenant/values-$(ENV).yaml -f $(TARGET_VALUES) \
	  --set image.repository=$(IMAGE_REPO) \
	  --set image.digest=$(or $(IMAGE_DIGEST),$$(make -s image-digest | sed 's/.*@//')) \
	  $(if $(and $(filter demo,$(ENV)),$(DEMO_OCI_NAMESPACE)),--set bronze.replica.endpoint=$(DEMO_OCI_ENDPOINT)) \
	  $(HELM_ATOMIC) --timeout $(HELM_TIMEOUT) $(HELM_EXTRA)

kubeconfig-oidc: ## Inside GitHub Actions: kubeconfig from the job's OIDC token + the public cluster CA (no stored credential)
	scripts/oidc_kube_context.sh $(OIDC_KUBECONFIG)

deploy-demo: ## Inside GitHub Actions: DEMO_OCI_NAMESPACE check → OIDC kubeconfig → deploy-tenant ENV=demo (the deploy-demo workflow's deploy step)
	@test -n "$(DEMO_OCI_NAMESPACE)" || { echo "deploy-demo: DEMO_OCI_NAMESPACE unset (repository variable: the OCI tenancy namespace, oci os ns get)"; exit 1; }
	$(MAKE) kubeconfig-oidc
	$(MAKE) deploy-tenant ENV=demo KUBECONFIG=$(OIDC_KUBECONFIG)

# ADR-035 amendment 1: cloud-init is first boot only (the servers ignore user_data changes), so a
# change to the authentication file or the namespace RBAC reaches the running demo server here.
DEMO_SSH ?= ssh -o BatchMode=yes -o ConnectTimeout=10
DEMO_TF_OUT = $(TF) -chdir=$(TF_DIR)/roots/hcloud output -raw

demo-reconfigure: ## Author, admin SSH key: push the rendered authn.yaml + namespace RBAC (Terraform outputs) to the demo server, restart k3s, wait for the API (ADR-035 amendment 1)
	@test -n "$(TF)" || { echo "demo-reconfigure: neither terraform nor tofu installed"; exit 1; }
	@tmp="$$(mktemp -d)"; trap 'rm -rf "$$tmp"' EXIT; \
	host="$$($(DEMO_TF_OUT) server_public_address)" || { echo "demo-reconfigure: no server_public_address in the hcloud state"; exit 1; }; \
	$(DEMO_TF_OUT) authn_yaml > "$$tmp/authn.yaml" || { echo "demo-reconfigure: no authn_yaml output"; exit 1; }; \
	$(DEMO_TF_OUT) rbac_yaml > "$$tmp/rbac.yaml" || { echo "demo-reconfigure: no rbac_yaml output (apply the outputs first)"; exit 1; }; \
	$(DEMO_SSH) "root@$$host" 'install -m 0600 /dev/stdin /etc/rancher/k3s/authn.yaml.new' < "$$tmp/authn.yaml" \
	  && $(DEMO_SSH) "root@$$host" 'install -m 0644 /dev/stdin /var/lib/rancher/k3s/server/manifests/energy-platform-rbac.yaml' < "$$tmp/rbac.yaml" \
	  && $(DEMO_SSH) "root@$$host" 'cp -a /etc/rancher/k3s/authn.yaml /etc/rancher/k3s/authn.yaml.prev && mv /etc/rancher/k3s/authn.yaml.new /etc/rancher/k3s/authn.yaml && systemctl restart k3s && for i in $$(seq 1 60); do k3s kubectl get --raw /readyz >/dev/null 2>&1 && exit 0; sleep 2; done; echo "k3s API not ready after 120 s" >&2; exit 1' \
	  || { echo "demo-reconfigure: FAILED (the previous file is /etc/rancher/k3s/authn.yaml.prev on the server)"; exit 1; }; \
	echo "demo-reconfigure: authn.yaml and the namespace RBAC pushed to $$host, k3s restarted, API ready"

helm-driver-migrate: ## Admin kubeconfig, once: copy $(RELEASE)'s Helm release records from Secrets to ConfigMaps (TENANT_HELM_DRIVER); DELETE_SECRETS=1 removes the Secrets after the history check
	NAMESPACE=$(NAMESPACE) RELEASE=$(RELEASE) KUBECTL=$(KUBECTL) HELM=$(HELM) DELETE_SECRETS=$(DELETE_SECRETS) scripts/helm_release_to_configmaps.sh

print-demo-secret-template: ## The kubectl command shape for the demo Secret (values come from the Terraform outputs and verify.env, never from the repo)
	@echo "kubectl -n $(NAMESPACE) create secret generic $(RELEASE) \\"
	@for k in $(DEMO_SECRET_KEYS); do echo "  --from-literal=$$k=... \\"; done
	@echo "  --dry-run=client -o yaml | kubectl apply -f -"
	@echo "# image pull secret for the private ghcr.io package (values-demo.yaml image.pullSecrets; a classic PAT with read:packages only):"
	@echo "kubectl -n $(NAMESPACE) create secret docker-registry ghcr-pull --docker-server=ghcr.io \\"
	@echo "  --docker-username=<github user> --docker-password=<PAT> --dry-run=client -o yaml | kubectl apply -f -"

rollback-drill: ## ADR-016 §6 / ADR-025 §5: two failing upgrades (smoke, storage probe) must roll back with schema and production data untouched
	KIND_CONTEXT=$(KIND_CONTEXT) NAMESPACE=$(NAMESPACE) RELEASE=$(RELEASE) HELM=$(HELM) KUBECTL=$(KUBECTL) deployment/local/drills/rollback.sh

KIND_VERSION ?= v0.33.0
HELM_VERSION ?= v4.3.0
# Terraform for the terraform-validate CI job: GitHub's ubuntu-latest ships neither terraform nor
# tofu (first CI run, 2026-09-23). The version is the author's, whose plans are Terraform's; the
# SHA-256 is from releases.hashicorp.com terraform_1.16.3_SHA256SUMS, re-checked on the download.
CI_TERRAFORM_VERSION := 1.16.3
CI_TERRAFORM_SHA256  := 093b6ae9a2228af5029c41606bc96eb583553528aad1bfe7e0b4d62fc91e25d8

ci-terraform: ## CI only: install Terraform $(CI_TERRAFORM_VERSION) (linux_amd64), checksum-verified
	curl -fsSLo /tmp/terraform.zip https://releases.hashicorp.com/terraform/$(CI_TERRAFORM_VERSION)/terraform_$(CI_TERRAFORM_VERSION)_linux_amd64.zip
	echo "$(CI_TERRAFORM_SHA256)  /tmp/terraform.zip" | sha256sum -c -
	unzip -o -q /tmp/terraform.zip terraform -d /tmp && sudo mv /tmp/terraform /usr/local/bin/terraform
	terraform version

ci-kind-tools: ## CI only: install kind and helm at pinned versions (the runner has docker and kubectl)
	curl -fsSLo /tmp/kind https://kind.sigs.k8s.io/dl/$(KIND_VERSION)/kind-linux-amd64 && chmod +x /tmp/kind && sudo mv /tmp/kind /usr/local/bin/kind
	curl -fsSL https://get.helm.sh/helm-$(HELM_VERSION)-linux-amd64.tar.gz | tar -xzO linux-amd64/helm > /tmp/helm && chmod +x /tmp/helm && sudo mv /tmp/helm /usr/local/bin/helm
	kind version && helm version --short

local-down: ## Tear the kind cluster down
	$(KIND) delete cluster --name $(KIND_NAME)

smoke-test: ## helm test (the smoke hook again) → one gaps+freshness run → freshness metric present → restore-drill dry run as a one-off Job
	$(HELM_KIND) test $(RELEASE) -n $(NAMESPACE) --logs --timeout 10m
	$(KUBE) -n $(NAMESPACE) delete job gaps-smoke --ignore-not-found >/dev/null
	$(KUBE) -n $(NAMESPACE) create job gaps-smoke --from=cronjob/$(RELEASE)-gaps >/dev/null
	$(KUBE) -n $(NAMESPACE) wait --for=condition=complete job/gaps-smoke --timeout=300s >/dev/null \
	  || { $(KUBE) -n $(NAMESPACE) logs job/gaps-smoke | tail -20; echo "smoke-test: FAIL — gaps+freshness run"; exit 1; }
	@echo "smoke-test: gaps + freshness row written"
	@$(KUBE) -n $(NAMESPACE) port-forward svc/$(RELEASE)-metrics 19187:9187 >/dev/null 2>&1 & pf=$$!; sleep 3; \
	  metrics="$$(curl -s --max-time 10 http://127.0.0.1:19187/metrics)"; kill $$pf 2>/dev/null || true; wait $$pf 2>/dev/null || true; \
	  echo "$$metrics" | grep -E '^energy_platform_freshness_age_seconds\{.*target="ote_intraday_market"' \
	    || { echo "smoke-test: FAIL — no freshness metric for ote_intraday_market (is the gaps CronJob running?)"; exit 1; }; \
	  echo "smoke-test: freshness metric present"
	$(KUBE) -n $(NAMESPACE) delete job restore-drill-dry-run --ignore-not-found >/dev/null
	$(KUBE) -n $(NAMESPACE) create job restore-drill-dry-run --from=cronjob/$(RELEASE)-restore-drill --dry-run=client -o json \
	  | python3 -c 'import json,sys; j=json.load(sys.stdin); s=j["spec"]["template"]["spec"]; [c.__setitem__("env",[{"name":"RESTORE_DRILL_ARGS","value":"--dry-run"} if e["name"]=="RESTORE_DRILL_ARGS" else e for e in c.get("env",[])]) for c in s["containers"]+s.get("initContainers",[])]; print(json.dumps(j))' \
	  | $(KUBE) -n $(NAMESPACE) apply -f - >/dev/null
	@for i in $$(seq 1 120); do \
	  state="$$($(KUBE) -n $(NAMESPACE) get job restore-drill-dry-run -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type}{end}' 2>/dev/null)"; \
	  case "$$state" in \
	    *Complete*) break;; \
	    *Failed*) $(KUBE) -n $(NAMESPACE) logs job/restore-drill-dry-run -c drill | tail -20; echo "smoke-test: FAIL — restore-drill dry run"; exit 1;; \
	  esac; sleep 5; \
	done; test -n "$$state" || { echo "smoke-test: FAIL — restore-drill dry run did not finish in 10 min"; exit 1; }
	$(KUBE) -n $(NAMESPACE) logs job/restore-drill-dry-run -c drill | tail -4
	@echo "smoke-test: OK (smoke hook, freshness metric, restore-drill dry run)"

demo: sync ## fixture → capture → Bronze → parse → map → Postgres → query, offline (ephemeral PostgreSQL unless ENERGY_PLATFORM_DSN is set)
	scripts/with_postgres.sh $(RUN) python -m energy_platform.cli demo

fixtures: sync ## Regenerate examples/fixtures (synthetic Bronze objects, deterministic)
	$(RUN) python -m scripts.make_example_fixtures

new-target: sync ## energyctl new-target ID=<id> MODALITY=<m> [DATASET=<dataset_id>]
	@test -n "$(ID)" -a -n "$(MODALITY)" || { echo "usage: make new-target ID=<id> MODALITY=<modality> [DATASET=<dataset_id>]"; exit 2; }
	$(RUN) python -m energy_platform.cli new-target $(ID) --modality $(MODALITY) $(if $(DATASET),--dataset $(DATASET),)

validate-targets: sync ## energyctl validate --all: admission + surface for every target (05 B-rows)
	$(RUN) python -m energy_platform.cli validate --all

migration-check: sync ## every migration has a real downgrade; linear chain (ADR-016 §3, 05 C-45)
	$(RUN) python -m scripts.check_migrations

workload-check: sync ## action pins, image digests, requests/limits on everything under deployment/ (A-8, ADR-016, 05 C-42…C-44)
	$(RUN) python -m scripts.check_workloads

harness-check: validate-targets migration-check workload-check ## the Phase 3 static gates (docs/05 §2)

pr-surface: sync ## a PR touching targets/<id>/ touches nothing else (ADR-022; 05 C-39…C-41). BASE=<ref> or PR_BASE env; no base → nothing to classify
	$(RUN) python -m scripts.check_pr_surface $(if $(BASE),--base $(BASE),)
