"""05 C-37, C-46 and the import-linter half of C-30: CI is `make`, live tests never run in CI,
CODEOWNERS covers the paths that constrain agents, targets may not import the fetch layer."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

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


def test_ci_workflow_only_calls_make() -> None:
    wf = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    for name, job in wf["jobs"].items():
        for step in job["steps"]:
            if "run" in step:
                assert step["run"].startswith("make "), f"{name}: {step['run']!r} bypasses Make"
                assert "pytest" not in step["run"] and "--live" not in step["run"]
            else:
                assert "uses" in step


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
