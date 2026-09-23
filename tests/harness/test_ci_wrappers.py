"""05 C-37, C-46 and the import-linter half of C-30: CI is `make`, live tests never run in CI,
CODEOWNERS covers the paths that constrain agents, targets may not import the fetch layer."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]


def _makefile_recipe(target: str) -> str:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(target)}:.*\n((?:\t.*\n)+)", text, re.MULTILINE)
    assert m, f"no recipe for {target}"
    return m.group(1)


def test_make_test_deselects_live() -> None:
    assert '-m "not live"' in _makefile_recipe("test")


def test_make_check_includes_every_static_gate() -> None:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"^check:\s*([^#\n]+)", text, re.MULTILINE)
    assert m
    deps = set(m.group(1).split())
    assert {"lint", "lock-check", "type", "test", "harness-check"} <= deps


WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=[w.name for w in WORKFLOWS])
def test_ci_workflow_only_calls_make(workflow: Path) -> None:
    wf = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for name, job in wf["jobs"].items():
        for step in job["steps"]:
            if "run" in step:
                assert step["run"].startswith("make "), f"{name}: {step['run']!r} bypasses Make"
                assert "pytest" not in step["run"] and "--live" not in step["run"]
            else:
                assert "uses" in step


def test_live_smoke_runs_only_on_a_schedule_never_on_pull_requests() -> None:
    """ADR-020: the nightly smoke is not PR CI; ci.yml never selects live tests (05 C-37)."""
    nightly = yaml.safe_load(
        (REPO / ".github" / "workflows" / "nightly-live-smoke.yml").read_text(encoding="utf-8")
    )
    triggers = nightly[True] if True in nightly else nightly["on"]  # YAML reads `on` as True
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    runs = {s["run"] for job in nightly["jobs"].values() for s in job["steps"] if "run" in s}
    assert "make live-smoke" in runs
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    ci_runs = {s["run"] for job in ci["jobs"].values() for s in job["steps"] if "run" in s}
    assert "make live-smoke" not in ci_runs
    assert "-m live" in _makefile_recipe("live-smoke")


def test_ci_has_a_job_per_phase_3_gate() -> None:
    wf = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    runs = {step["run"] for job in wf["jobs"].values() for step in job["steps"] if "run" in step}
    assert {"make harness-check", "make pr-surface", "make lint", "make test"} <= runs


def test_pr_surface_job_gets_the_base_sha() -> None:
    wf = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = wf["jobs"]["pr-surface"]
    step = next(s for s in job["steps"] if s.get("run") == "make pr-surface")
    assert step["env"]["PR_BASE"] == "${{ github.event.pull_request.base.sha }}"
    checkout = next(s for s in job["steps"] if "uses" in s)
    assert checkout["with"]["fetch-depth"] == 0


def test_import_linter_forbids_fetch_from_targets() -> None:
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = cfg["tool"]["importlinter"]["contracts"]
    by_name = {c["name"]: c for c in contracts}
    targets = by_name["targets may import only energy_platform.contracts"]
    assert targets["source_modules"] == ["targets"]
    assert {"energy_platform.fetch", "energy_platform.mapping", "energy_platform.mcp"} <= set(
        targets["forbidden_modules"]
    )
    assert by_name["energy_platform never imports targets"]["forbidden_modules"] == ["targets"]


def test_codeowners_covers_the_protected_paths() -> None:
    owned = {
        line.split()[0]
        for line in (REPO / "CODEOWNERS").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for path in (
        "/energy_platform/",
        "/energy_platform/contracts/registry.py",
        "/energy_platform/contracts/hosts.py",
        "/deployment/",
        "/docs/adr/",
        "/deps-allowlist.txt",
        "/pyproject.toml",
        "/Makefile",
        "/.github/",
        "/CODEOWNERS",
    ):
        assert path in owned, path


def test_banned_api_list_covers_every_egress_path() -> None:
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    banned = set(cfg["tool"]["ruff"]["lint"]["flake8-tidy-imports"]["banned-api"])
    assert {
        "httpx",
        "requests",
        "urllib.request",
        "urllib3",
        "aiohttp",
        "http",
        "http.client",
        "socket",
        "ssl",
        "subprocess",
        "importlib",
        "ctypes",
    } <= banned
    ignores = cfg["tool"]["ruff"]["lint"]["per-file-ignores"]
    exempt = {k for k, v in ignores.items() if "TID251" in v}
    assert exempt == {"scripts/**", "conftest.py", "tests/harness/**", "energy_platform/fetch/**"}


def test_deploy_demo_workflow_uses_oidc_and_nothing_stored() -> None:
    """ADR-015 federation clause / V-14: the deploy job holds id-token only, the image job
    packages only (plan P5-D20); nothing stored; on push to main (paths that change what the
    demo runs) and by hand, never on a pull request (Phase 9, G6)."""
    wf = yaml.safe_load(
        (REPO / ".github" / "workflows" / "deploy-demo.yml").read_text(encoding="utf-8")
    )
    triggers = wf[True] if True in wf else wf["on"]
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["main"]
    paths = set(triggers["push"]["paths"])
    assert {"energy_platform/**", "targets/**", "deployment/helm/**", "uv.lock"} <= paths
    assert ".github/workflows/deploy-demo.yml" in paths
    assert "docs/**" not in paths  # a docs-only push does not rebuild
    assert wf["permissions"] == {"contents": "read"}
    image, deploy = wf["jobs"]["image"], wf["jobs"]["deploy"]
    assert image["permissions"] == {"contents": "read", "packages": "write"}
    assert deploy["permissions"] == {"contents": "read", "id-token": "write"}
    assert [s["run"] for s in image["steps"] if "run" in s] == ["make image-push"]
    assert image["env"]["IMAGE_PLATFORM"] == "linux/amd64"  # the demo's cx23 nodes
    assert "github.token" in image["env"]["REGISTRY_TOKEN"]  # the job's own; expires with it
    assert deploy["needs"] == "image"
    assert [s["run"] for s in deploy["steps"] if "run" in s] == [
        "make ci-bootstrap",
        "make deploy-demo",
    ]
    assert deploy["env"]["IMAGE_DIGEST"] == "${{ needs.image.outputs.digest }}"
    text = (REPO / ".github" / "workflows" / "deploy-demo.yml").read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "${{ vars.DEMO_CLUSTER_URL }}" in str(deploy["env"]["DEMO_CLUSTER_URL"])


def test_tenant_deploy_keeps_helm_records_in_configmaps() -> None:
    """ADR-035 amendment 1: the deploy Role has no `secrets` verbs, so the tenant deploy must
    store Helm's release records as ConfigMaps (the default driver would need Secrets)."""
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^TENANT_HELM_DRIVER \?= configmap$", text, re.MULTILINE)
    recipe = text.split("\ndeploy-tenant:", 1)[1].split("\n\n", 1)[0]
    assert "HELM_DRIVER=$(TENANT_HELM_DRIVER) $(HELM) upgrade --install" in recipe
    rbac = (
        REPO / "deployment" / "own-cluster" / "terraform" / "cloud-init" / "rbac.yaml.tftpl"
    ).read_text(encoding="utf-8")
    resources = [line for line in rbac.splitlines() if line.strip().startswith("resources:")]
    assert not [r for r in resources if re.search(r"\bsecrets\b|pods/exec|pods/portforward", r)]


def test_no_ci_reachable_recipe_pipes_a_download_into_a_shell() -> None:
    """Threat model §3: every tool CI installs is a pinned artefact checked against a pinned
    SHA-256 (`ci-bootstrap` for uv, `ci-terraform`); `curl … | sh` runs whatever the URL
    serves that day."""
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    assert not re.search(r"\|\s*(ba|z|da)?sh\b", text), "a download piped into a shell"
    assert re.search(r"^UV_SHA256\s+\?= [0-9a-f]{64}$", text, re.MULTILINE)
    recipe = text.split("\nci-bootstrap:", 1)[1].split("\n\n", 1)[0]
    assert "releases/download/$(UV_VERSION)/" in recipe
    assert 'echo "$(UV_SHA256)  /tmp/uv.tar.gz" | sha256sum -c -' in recipe


def test_makefile_values_carry_no_trailing_comment() -> None:
    """Make keeps the spaces before a trailing `#` in a value (`UV_VERSION ?= 0.11.7   # …`
    broke the ci-bootstrap installer URL): a non-empty assignment ends at its value."""
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    bad = [
        line for line in text.splitlines() if re.match(r"^[A-Z_]+\s*[?:]?=\s*\S[^#]*?\s+#", line)
    ]
    assert bad == [], bad


def test_agents_md_mirrors_claude_md() -> None:
    """Claude Code reads CLAUDE.md, Codex and other agents read AGENTS.md: one text, or the agents
    work to different rules (Phase 7 finding F-2: AGENTS.md had an older command list)."""
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert (REPO / "AGENTS.md").read_text(encoding="utf-8") == claude
    assert "Contributor sessions" in claude  # Phase 7 finding F-1
