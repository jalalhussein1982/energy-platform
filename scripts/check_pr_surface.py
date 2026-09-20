"""Fail a pull request that touches a target and anything else (ADR-022; 05 C-39…C-41).

Usage: check_pr_surface.py [--base <ref>]   (or env PR_BASE). Without a base — a push to main,
a local run — there is no PR to classify: the script says so and exits 0 (Makefile convention).
CI passes ``github.event.pull_request.base.sha``; the diff is ``<base>...HEAD``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from energy_platform.harness.pr_surface import classify, report


def changed_files(base: str) -> list[str]:
    git = shutil.which("git") or "/usr/bin/git"
    out = subprocess.run(  # noqa: S603 — fixed argv, resolved git path, base from CI
        [git, "diff", "--name-only", "--diff-filter=ACDMRT", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    base = os.environ.get("PR_BASE", "")
    if len(argv) >= 3 and argv[1] == "--base":
        base = argv[2]
    if not base:
        print("pr-surface: no base ref (not a pull request) — nothing to classify")
        return 0
    try:
        paths = changed_files(base)
    except subprocess.CalledProcessError as exc:
        print(f"pr-surface: git diff against {base!r} failed: {exc.stderr.strip()}")
        return 1
    surface = classify(paths)
    print("\n".join(report(surface)))
    return 0 if surface.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
