"""``open_pr`` / ``energyctl pr-bundle``: a pull request prepared, not pushed (P3-D2; 05 C-51).

Platform code may not run ``git`` (ADR-027 §3), and pushing is the Level-2 boundary of ADR-006.
So the harness produces a self-contained **bundle**: one target's files, the gate results that
were green when it was made (surface, admission, goldens — **not** the target's pytest, lint or
types, which the sandbox cannot run and CI does; the bundle says so, review 2 AE-03), a title
and a body. ``scripts/apply_pr_bundle.py`` (git allowed
there) turns it into a branch and a commit outside the sandbox; a human or the CI bot pushes.
A bundle is refused while any of its gates is red, so a red target cannot even ask for review;
CI is the boundary for the checks the bundle does not run.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from energy_platform.bronze import sha256_hex
from energy_platform.contracts.manifest import ManifestSyntaxError, load_manifest, validate_manifest
from energy_platform.harness.goldens import run_target
from energy_platform.harness.pr_surface import classify
from energy_platform.harness.surface import check_target, unloadable_parser

BUNDLE_VERSION = 1
NOT_RUN_BY_BUNDLE: tuple[str, ...] = ("target pytest", "ruff", "mypy")


class BundleRefused(ValueError):
    """Every reason a PR must not be opened, in one message."""


@dataclass(frozen=True, slots=True)
class Bundle:
    path: Path
    target_id: str
    branch: str
    files: tuple[str, ...]


def gate_report(target: Path) -> dict[str, object]:
    """The gates a Route A PR must pass, as data (05 §2): surface, admission, goldens.

    ``not_run`` names the checks this report does **not** cover (the target's pytest, ruff,
    mypy): ``energyctl run-target-tests`` and CI run them. A green report is a partial verdict.
    """
    surface = check_target(target) + unloadable_parser(target)
    try:
        manifest = load_manifest(target / "manifest.yaml")
        validation = validate_manifest(manifest).model_dump(mode="json")
    except (ManifestSyntaxError, ValidationError, OSError) as exc:
        validation = {"status": "INVALID", "errors": [str(exc)], "missing": {}}
    goldens = [
        {"golden": g.golden, "fixture": g.fixture, "ok": g.ok, "problems": list(g.problems)}
        for g in run_target(target)
    ]
    ok = (
        not surface
        and validation["status"] == "OK"
        and bool(goldens)
        and all(g["ok"] for g in goldens)
    )
    return {
        "ok": ok,
        "surface": surface,
        "validation": validation,
        "goldens": goldens,
        "not_run": list(NOT_RUN_BY_BUNDLE),
    }


def _files_of(target: Path) -> list[Path]:
    return sorted(p for p in target.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def prepare_bundle(
    repo: Path,
    target_id: str,
    outbox: Path,
    *,
    title: str | None = None,
    body: str = "",
    touched: tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> Bundle:
    """Refuse unless the session touched one target only and every gate is green."""
    target = repo / "targets" / target_id
    if not (target / "manifest.yaml").is_file():
        raise BundleRefused(f"targets/{target_id}/manifest.yaml does not exist")
    files = _files_of(target)
    rel = tuple(p.relative_to(repo).as_posix() for p in files)
    surface = classify(list(touched) if touched is not None else list(rel))
    if not surface.ok or surface.kind != "target" or surface.target_id != target_id:
        problems = list(surface.problems) or [f"the changes are not a target PR for {target_id}"]
        raise BundleRefused("not a Route A change set:\n  " + "\n  ".join(problems))
    gates = gate_report(target)
    if not gates["ok"]:
        raise BundleRefused(
            "gates are red; fix them before asking for review:\n" + json.dumps(gates, indent=2)
        )
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    branch = f"target/{target_id}"
    bundle = {
        "bundle_version": BUNDLE_VERSION,
        "created_at": stamp,
        "target_id": target_id,
        "branch": branch,
        "title": title or f"feat(target): {target_id} (Route A, ADR-022)",
        "body": body
        or (
            f"Adds `targets/{target_id}/` only (manifest, fixtures, goldens, tests). "
            "Surface, admission and golden gates were green when this bundle was prepared. "
            "Not run by pr-bundle: the target's pytest, ruff and mypy — CI runs them and is the "
            "gate for them.\n\n"
            "Route A adapter addition (ADR-022). No registry, platform or deployment change."
        ),
        "gates": gates,
        "files": [
            {
                "path": path,
                "sha256": sha256_hex(p.read_bytes()),
                "content_b64": base64.b64encode(p.read_bytes()).decode("ascii"),
            }
            for path, p in zip(rel, files, strict=True)
        ],
    }
    outbox.mkdir(parents=True, exist_ok=True)
    out = outbox / f"{target_id}-{stamp}.json"
    out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return Bundle(out, target_id, branch, rel)


def load_bundle(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("bundle_version") != BUNDLE_VERSION:
        raise BundleRefused(f"{path}: not a bundle (version {BUNDLE_VERSION})")
    return data


def verify_bundle(data: dict[str, object]) -> list[str]:
    """Paths confined to one target; contents match their hashes (a bundle is untrusted input)."""
    problems: list[str] = []
    target_id = str(data.get("target_id", ""))
    files = data.get("files")
    if not isinstance(files, list) or not files:
        return ["bundle has no files"]
    prefix = f"targets/{target_id}/"
    for item in files:
        if not isinstance(item, dict):
            problems.append("file entry is not a mapping")
            continue
        path = str(item.get("path", ""))
        if not path.startswith(prefix) or ".." in Path(path).parts or path.startswith("/"):
            problems.append(f"{path}: outside {prefix}")
        try:
            content = base64.b64decode(str(item.get("content_b64", "")), validate=True)
        except (ValueError, TypeError):
            problems.append(f"{path}: content is not base64")
            continue
        if sha256_hex(content) != item.get("sha256"):
            problems.append(f"{path}: content does not match its sha256")
    surface = classify([str(i.get("path", "")) for i in files if isinstance(i, dict)])
    if not surface.ok or surface.target_id != target_id:
        problems.extend(surface.problems or ("files are not one target's",))
    return problems
