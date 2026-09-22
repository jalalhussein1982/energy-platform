"""Render the chart's ``targets:`` values from ``targets/*/manifest.yaml`` (Phase 5 plan P5-D3).

Helm cannot read outside its chart directory, and a target PR may touch only ``targets/<id>/``
(ADR-022, 05 C-39…C-41), so nothing generated is committed: every deploy Make target and
``make helm-lint`` run this at deploy time and pass the output with ``-f``. The CronJob template
then renders capture / process (/ recapture) per target — "one template, rendered once per
target from the manifests" (ADR-003 rev.) stays literally true.

A manifest whose ``license`` starts with ``restricted`` is refused: the scheduler never runs a
source the platform may not redistribute (P4-D11; 05 C-55). Exit 1 names the target.

Usage: render_target_values.py [targets-root]   (default: targets/)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from energy_platform.contracts.manifest import ManifestSyntaxError, load_manifest
from energy_platform.harness.surface import target_dirs

RESTRICTED = "restricted"


def target_values(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """``(targets, problems)``: one entry per manifest, in id order."""
    targets: list[dict[str, Any]] = []
    problems: list[str] = []
    for directory in target_dirs(root):
        path = directory / "manifest.yaml"
        if not path.is_file():
            problems.append(f"{directory}: no manifest.yaml")
            continue
        try:
            m = load_manifest(path)
        except (ManifestSyntaxError, ValidationError, OSError) as exc:
            problems.append(f"{path}: {exc}")
            continue
        if m.license.strip().lower().startswith(RESTRICTED):
            problems.append(
                f"{m.target_id}: license {m.license!r} is restricted — never scheduled (05 C-55)"
            )
            continue
        entry: dict[str, Any] = {
            "id": m.target_id,
            "manifest": f"{m.target_id}/manifest.yaml",
            "cron": m.cadence.cron,
            "timezone": m.cadence.timezone,
            "correction": None,
            "hosts": sorted(m.allowed_hosts),
        }
        if m.cadence.correction is not None:
            entry["correction"] = {
                "cron": m.cadence.correction.cron,
                "days": m.cadence.correction.days,
            }
        targets.append(entry)
    return targets, problems


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("targets")
    targets, problems = target_values(root)
    if problems:
        print("render_target_values: refused:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(yaml.safe_dump({"targets": targets}, sort_keys=False), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
