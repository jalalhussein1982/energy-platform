"""Render the chart's ``targets:`` values from ``targets/*/manifest.yaml`` (Phase 5 plan P5-D3).

Helm cannot read outside its chart directory, and a target PR may touch only ``targets/<id>/``
(ADR-022, 05 C-39…C-41), so nothing generated is committed: every deploy Make target and
``make helm-lint`` run this at deploy time and pass the output with ``-f``. The CronJob template
then renders capture / process (/ recapture) per target — "one template, rendered once per
target from the manifests" (ADR-003 rev.) stays literally true.

A manifest whose ``license`` starts with ``restricted`` is refused: the scheduler never runs a
source the platform may not redistribute (P4-D11; 05 C-55). Exit 1 names the target.

``process`` runs on the same cadence as ``capture`` but ``--process-offset`` minutes later
(default 3), so a process pod never races the capture of the same instant; ``recapture``
keeps the manifest's correction cron.

Usage: render_target_values.py [targets-root] [--process-offset N]   (default: targets/, 3)
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


def shift_cron_minutes(cron: str, offset: int) -> str:
    """Shift the minute field of a five-field cron by ``offset`` (0..59) where that keeps the
    meaning: ``*/N`` → ``off-59/N``; ``a,b`` → each +off; ``M`` → M+off; anything that would
    wrap past 59 or is not one of those forms is returned unchanged."""
    fields = cron.split()
    if len(fields) != 5 or offset <= 0:
        return cron
    minute = fields[0]
    if minute == "*":
        shifted = f"{offset}-59/1" if offset else "*"
    elif minute.startswith("*/") and minute[2:].isdigit():
        step = int(minute[2:])
        if offset >= step:
            return cron
        shifted = f"{offset}-59/{step}"
    elif all(part.isdigit() for part in minute.split(",")):
        values = [int(part) + offset for part in minute.split(",")]
        if max(values) > 59:
            return cron
        shifted = ",".join(str(v) for v in values)
    else:
        return cron
    return " ".join([shifted, *fields[1:]])


def target_values(root: Path, *, process_offset: int = 3) -> tuple[list[dict[str, Any]], list[str]]:
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
            "process_cron": shift_cron_minutes(m.cadence.cron, process_offset),
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
    args = [a for a in argv[1:] if not a.startswith("--")]
    offset = 3
    if "--process-offset" in argv:
        offset = int(argv[argv.index("--process-offset") + 1])
        args = [a for a in args if a != str(offset)]
    root = Path(args[0]) if args else Path("targets")
    targets, problems = target_values(root, process_offset=offset)
    if problems:
        print("render_target_values: refused:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(yaml.safe_dump({"targets": targets}, sort_keys=False), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
