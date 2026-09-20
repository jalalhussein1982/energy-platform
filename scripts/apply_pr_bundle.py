"""Turn a PR bundle into a branch and a commit; push only when asked (P3-D2; 05 C-53).

Runs outside the sandbox (git is allowed in scripts/). It verifies the bundle (paths confined to
``targets/<id>/``, hashes match), checks out ``target/<id>`` from the current HEAD, writes the
files, commits, and stops. ``--push`` pushes that branch to ``origin``; nothing here ever
commits on ``main`` or merges. Opening the pull request is a human's (or the CI bot's) step:
``gh pr create --base main --head target/<id>``.

Usage: apply_pr_bundle.py <bundle.json> [--repo DIR] [--push]
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path

from energy_platform.harness.pr import BundleRefused, load_bundle, verify_bundle

PROTECTED_BRANCHES = {"main", "master"}


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git") or "/usr/bin/git"
    return subprocess.run(  # noqa: S603 — fixed argv, resolved git path
        [git, *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def apply(bundle_path: Path, repo: Path, *, push: bool = False) -> str:
    data = load_bundle(bundle_path)
    problems = verify_bundle(data)
    if problems:
        raise BundleRefused("bundle refused:\n  " + "\n  ".join(problems))
    branch = str(data["branch"])
    if branch in PROTECTED_BRANCHES or not branch.startswith("target/"):
        raise BundleRefused(f"bundle branch {branch!r} must be target/<id>")
    if _git(repo, "status", "--porcelain"):
        raise BundleRefused("working tree is not clean; commit or stash first")
    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if current in PROTECTED_BRANCHES:
        _git(repo, "checkout", "-q", "-b", branch)
    elif current != branch:
        _git(repo, "checkout", "-q", "-b", branch)
    files = data["files"]
    assert isinstance(files, list)
    for item in files:
        path = repo / str(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(str(item["content_b64"])))
        _git(repo, "add", "--", str(item["path"]))
    _git(repo, "commit", "-q", "-m", f"{data['title']}\n\n{data['body']}")
    if push:
        _git(repo, "push", "-u", "origin", branch)
    return branch


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    bundle = Path(argv[1])
    repo = Path(".")
    push = "--push" in argv
    if "--repo" in argv:
        repo = Path(argv[argv.index("--repo") + 1])
    try:
        branch = apply(bundle, repo, push=push)
    except (BundleRefused, subprocess.CalledProcessError, OSError) as exc:
        print(f"apply-pr-bundle: {exc}")
        return 1
    print(f"apply-pr-bundle: committed on {branch}" + (" and pushed" if push else ""))
    print(f"next: gh pr create --base main --head {branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
