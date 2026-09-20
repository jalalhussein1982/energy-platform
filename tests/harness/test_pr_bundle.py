"""05 C-51, C-53: bundles only for green targets; applying never touches main or pushes."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from scripts.apply_pr_bundle import apply, main

from energy_platform.harness.pr import BundleRefused, gate_report, prepare_bundle, verify_bundle
from tests.harness.targets_builder import make_target


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "targets").mkdir(parents=True)
    (root / "targets" / "__init__.py").write_text("")
    return root


def test_gate_report_and_bundle_for_a_green_target(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    make_target(root / "targets", "ote_probe")
    assert gate_report(root / "targets" / "ote_probe")["ok"] is True
    bundle = prepare_bundle(root, "ote_probe", tmp_path / "outbox")
    data = json.loads(bundle.path.read_text())
    assert data["target_id"] == "ote_probe" and data["branch"] == "target/ote_probe"
    assert verify_bundle(data) == []
    assert (
        set(bundle.files) == {f["path"] for f in data["files"]}
        and "targets/ote_probe/manifest.yaml" in bundle.files
    )


def test_bundle_refused_when_red_or_mixed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    t = make_target(root / "targets", "ote_probe")
    with pytest.raises(BundleRefused, match="not a Route A"):
        prepare_bundle(
            root,
            "ote_probe",
            tmp_path / "o",
            touched=("targets/ote_probe/README.md", "energy_platform/contracts/registry.py"),
        )
    (t / "fetch.py").write_text("x = 1\n")
    with pytest.raises(BundleRefused, match="gates are red"):
        prepare_bundle(root, "ote_probe", tmp_path / "o")
    with pytest.raises(BundleRefused, match="does not exist"):
        prepare_bundle(root, "ghost", tmp_path / "o")


def test_verify_bundle_rejects_tampering(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    make_target(root / "targets", "ote_probe")
    data = json.loads(prepare_bundle(root, "ote_probe", tmp_path / "o").path.read_text())
    data["files"][0]["content_b64"] = base64.b64encode(b"evil").decode()
    assert any("sha256" in p for p in verify_bundle(data))
    data["files"][0]["path"] = "energy_platform/contracts/registry.py"
    assert any("outside targets/ote_probe/" in p for p in verify_bundle(data))
    data["files"] = []
    assert verify_bundle(data) == ["bundle has no files"]


# ------------------------------------------------------------------ apply (git)


def _git(cwd: Path, *args: str) -> str:
    git = shutil.which("git") or "/usr/bin/git"
    return subprocess.run(  # noqa: S603 — fixed argv in a temporary repository
        [git, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
            "HOME": str(cwd),
            "PATH": "/usr/bin:/bin",
        },
    ).stdout.strip()


def test_apply_never_touches_main(tmp_path: Path) -> None:
    src = _repo(tmp_path)
    make_target(src / "targets", "ote_probe")
    bundle = prepare_bundle(src, "ote_probe", tmp_path / "outbox").path
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "-q", "-b", "main")
    (checkout / "README.md").write_text("x\n")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-q", "-m", "base")
    main_sha = _git(checkout, "rev-parse", "main")
    branch = apply(bundle, checkout)
    assert branch == "target/ote_probe"
    assert _git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "target/ote_probe"
    assert _git(checkout, "rev-parse", "main") == main_sha  # main untouched
    assert (checkout / "targets" / "ote_probe" / "manifest.yaml").is_file()
    assert "targets/ote_probe/manifest.yaml" in _git(
        checkout, "show", "--name-only", "--format=", "HEAD"
    )
    assert _git(checkout, "status", "--porcelain") == ""


def test_apply_refuses_tampered_bundle_and_dirty_tree(tmp_path: Path) -> None:
    src = _repo(tmp_path)
    make_target(src / "targets", "ote_probe")
    bundle = prepare_bundle(src, "ote_probe", tmp_path / "outbox").path
    data = json.loads(bundle.read_text())
    data["branch"] = "main"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "-q", "-b", "main")
    with pytest.raises(BundleRefused, match="target/<id>"):
        apply(bad, checkout)
    (checkout / "dirty.txt").write_text("x\n")
    with pytest.raises(BundleRefused, match="not clean"):
        apply(bundle, checkout)
    assert main(["x", str(bad), "--repo", str(checkout)]) == 1
    assert main(["x"]) == 2
