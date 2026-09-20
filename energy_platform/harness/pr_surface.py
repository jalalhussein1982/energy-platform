"""PR surface classification (ADR-022 Route A/B, ADR-006; 05 C-39…C-41).

A pull request is a *target PR* when it touches anything under ``targets/<id>/``; then every
changed path must lie under that one directory. A PR that touches no target is a *platform PR*
and passes this gate (CODEOWNERS is its control). Protected platform paths are named in the
report so that "registry edit inside a target PR" is visible as such, not as a generic mix.
``scripts/check_pr_surface.py`` feeds it ``git diff --name-only``; the MCP ``open_pr`` tool
feeds it the session journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

Kind = Literal["platform", "target", "invalid", "empty"]

PROTECTED: dict[str, str] = {
    "energy_platform/contracts/registry.py": "dataset/metric registry (ADR-022 Route B)",
    "energy_platform/contracts/hosts.py": "host registry (ADR-026)",
    "deps-allowlist.txt": "dependency allowlist (ADR-006)",
    "pyproject.toml": "lint/type/test configuration (ADR-014)",
    "Makefile": "CI gates (ADR-015)",
    "CODEOWNERS": "ownership (ADR-006)",
    "conftest.py": "network block and collection rules (ADR-027 §4)",
}
PROTECTED_PREFIXES: dict[str, str] = {
    ".github/": "CI workflows (ADR-015)",
    "docs/adr/": "architecture decisions",
    "deployment/": "deployment (ADR-006)",
    "scripts/": "CI gate scripts",
    "energy_platform/": "platform code (ADR-005: semantics live here)",
}


@dataclass(frozen=True, slots=True)
class PrSurface:
    kind: Kind
    target_id: str | None
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.kind != "invalid"


def _target_of(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    if len(parts) >= 3 and parts[0] == "targets":
        return parts[1]
    return None


def _protected_reason(path: str) -> str | None:
    if path in PROTECTED:
        return PROTECTED[path]
    for prefix, reason in PROTECTED_PREFIXES.items():
        if path.startswith(prefix):
            return reason
    return None


def classify(paths: list[str] | tuple[str, ...]) -> PrSurface:
    normalised = sorted({p.strip().replace("\\", "/") for p in paths if p.strip()})
    if not normalised:
        return PrSurface("empty", None, ())
    targets = sorted({t for t in (_target_of(p) for p in normalised) if t is not None})
    if not targets:
        return PrSurface("platform", None, ())
    problems: list[str] = []
    if len(targets) > 1:
        problems.append(
            f"a target PR touches one target; this one touches {targets} (05 C-41) — split it"
        )
    target = targets[0] if len(targets) == 1 else None
    for path in normalised:
        if _target_of(path) is not None and (target is None or _target_of(path) == target):
            continue
        reason = _protected_reason(path)
        if reason is not None:
            problems.append(
                f"{path}: {reason} — never inside a target PR (05 C-40); open a platform PR"
            )
        elif _target_of(path) is None:
            problems.append(f"{path}: outside targets/{target or '<id>'}/ (05 C-39)")
    if problems:
        return PrSurface("invalid", target, tuple(problems))
    return PrSurface("target", target, ())


def report(surface: PrSurface) -> list[str]:
    if surface.kind == "empty":
        return ["pr-surface: no changed files"]
    if surface.kind == "platform":
        return ["pr-surface: platform PR (no target touched) — CODEOWNERS review applies"]
    if surface.kind == "target":
        return [f"pr-surface: target PR for targets/{surface.target_id}/ — OK"]
    return ["pr-surface: REJECTED (ADR-022 Route A touches targets/<id>/ only):"] + [
        f"  {p}" for p in surface.problems
    ]
