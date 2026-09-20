"""The eight ADR-007 tools and their guards (05 C-47…C-53).

Every tool is a method on :class:`Tools`; the server dispatches by name and passes the
arguments as a mapping. Guards, in one place:

- reads are confined to the checkout and refuse ``.git``, secrets and anything outside;
- writes go only to ``targets/<id>/`` paths that the surface rules accept, are checked before
  they are kept (a rejected write leaves no file), and are journaled for ``open_pr``;
- ``record_fixture`` may touch the network only when the server was started with
  ``allow_network=True`` (``energyctl mcp-serve --allow-network``);
- ``open_pr`` refuses unless the journal names exactly one target and every gate is green; it
  produces a bundle in the outbox, never a push (P3-D2).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from energy_platform.contracts.manifest import (
    ManifestSyntaxError,
    Modality,
    load_manifest,
    validate_manifest,
)
from energy_platform.harness.fixtures import FixtureError, record_from_file, record_live
from energy_platform.harness.pr import BundleRefused, prepare_bundle
from energy_platform.harness.runner import run_target_tests
from energy_platform.harness.scaffold import ScaffoldError, scaffold_target
from energy_platform.harness.surface import (
    TARGET_ID,
    check_target,
    completeness,
    fixture_names,
    golden_paths,
)

TOOL_NAMES: tuple[str, ...] = (
    "read_repository",
    "inspect_target",
    "scaffold_target",
    "write_target_file",
    "validate_target",
    "record_fixture",
    "run_target_tests",
    "open_pr",
)

READ_ROOTS = ("docs", "targets", "examples", "schemas", "README.md", "CLAUDE.md", "AGENTS.md")
DENY_PARTS = frozenset({".git", ".venv", "__pycache__", ".env", "secrets", ".ssh", ".kube"})
DENY_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".jks", ".crt", ".lock"})
DENY_NAMES = re.compile(r"^(\.env.*|.*secret.*|.*credential.*|id_rsa.*|kubeconfig.*)$", re.I)
MAX_READ = 64 * 1024
MAX_WRITE = 2 * 1024 * 1024
MAX_LIST = 500

MODALITIES: tuple[Modality, ...] = ("soap-xml", "dated-file", "html-table", "rest-json", "rest-xml")


class ToolError(ValueError):
    """Refused by a guard or failed; the agent sees the reason, never a traceback."""


def _schema(**props: dict[str, Any]) -> dict[str, Any]:
    required = [k for k, v in props.items() if v.pop("_required", False)]
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _s(desc: str, *, required: bool = False, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "string", "description": desc, **extra}
    if required:
        out["_required"] = True
    return out


TOOL_SPECS: dict[str, tuple[str, dict[str, Any]]] = {
    "read_repository": (
        "List a directory or read a file under docs/, targets/, examples/, schemas/ or the "
        "top-level README/CLAUDE.md (Level 0). Secrets, .git and anything outside are refused.",
        _schema(
            path=_s("repository-relative path; a directory lists, a file reads", required=True)
        ),
    ),
    "inspect_target": (
        "Manifest summary, validation result, surface problems, fixtures and goldens of a target.",
        _schema(target_id=_s("target id", required=True)),
    ),
    "scaffold_target": (
        "Create targets/<id>/ with exactly the ADR-027 surface (placeholders included).",
        _schema(
            target_id=_s("target id ^[a-z][a-z0-9_]{2,63}$", required=True),
            modality=_s("one of " + ", ".join(MODALITIES), required=True, enum=list(MODALITIES)),
            dataset_id=_s("registered dataset_id to fill from (optional)"),
            host=_s("source hostname (optional)"),
            with_parser={"type": "boolean", "description": "add a parser.py skeleton"},
        ),
    ),
    "write_target_file": (
        "Write one file inside targets/<id>/ (manifest.yaml, parser.py, README.md, tests/…). "
        "The surface rules run on the result; a rejected write is rolled back.",
        _schema(
            target_id=_s("target id", required=True),
            path=_s("path relative to targets/<id>/", required=True),
            content=_s("full file content", required=True),
        ),
    ),
    "validate_target": (
        "energyctl validate <id>: structural + admission result (OK | INVALID | ADMISSION_REQUIRED "
        "with the exact registry gaps) and surface problems.",
        _schema(target_id=_s("target id", required=True)),
    ),
    "record_fixture": (
        "Write targets/<id>/fixtures/<name>/ as a Bronze object. `payload_path` wraps a saved "
        "payload offline; `live: true` fetches once and needs the server's --allow-network.",
        _schema(
            target_id=_s("target id", required=True),
            name=_s("fixture name, e.g. ordinary_day", required=True),
            payload_path=_s("repository-relative path of a saved payload (offline mode)"),
            live={"type": "boolean", "description": "fetch from the source (opt-in)"},
            scheduled_for=_s("ISO 8601 instant with offset"),
            content_type=_s("content type for payload_path mode"),
        ),
    ),
    "run_target_tests": (
        "Surface rules, every golden through the platform pipeline, then the target's pytest.",
        _schema(target_id=_s("target id", required=True)),
    ),
    "open_pr": (
        "Prepare a Route A pull request for the one target this session touched: refuses if "
        "any gate is red; writes a bundle to the outbox for a human/CI to push (never pushes).",
        _schema(
            target_id=_s("target id", required=True),
            title=_s("PR title (optional)"),
            body=_s("PR body (optional)"),
        ),
    ),
}


def tool_definitions() -> list[dict[str, Any]]:
    out = []
    for name in TOOL_NAMES:
        desc, schema = TOOL_SPECS[name]
        out.append(
            {"name": name, "description": desc, "inputSchema": json.loads(json.dumps(schema))}
        )
    return out


@dataclass
class Tools:
    repo: Path
    outbox: Path
    allow_network: bool = False
    journal: dict[str, set[str]] = field(default_factory=dict)
    fetcher_factory: Callable[[], Any] | None = None

    def __post_init__(self) -> None:
        self.repo = self.repo.resolve()

    # ------------------------------------------------------------ dispatch

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise ToolError(f"unknown tool {name!r}; tools are {list(TOOL_NAMES)}")
        handler: Callable[..., dict[str, Any]] = getattr(self, name)
        return handler(**dict(arguments))

    # ------------------------------------------------------------ guards

    def _target(self, target_id: str) -> Path:
        if not isinstance(target_id, str) or not TARGET_ID.match(target_id):
            raise ToolError(f"target id must match {TARGET_ID.pattern}")
        return self.repo / "targets" / target_id

    def _existing_target(self, target_id: str) -> Path:
        target = self._target(target_id)
        if not (target / "manifest.yaml").is_file():
            raise ToolError(f"targets/{target_id}/ does not exist (scaffold_target first)")
        return target

    def _confine(self, rel: str) -> Path:
        if not isinstance(rel, str) or not rel or rel.startswith(("/", "~")) or "\\" in rel:
            raise ToolError(f"path must be repository-relative: {rel!r}")
        candidate = (self.repo / rel).resolve()
        if candidate != self.repo and self.repo not in candidate.parents:
            raise ToolError(f"{rel!r} is outside the repository")
        parts = candidate.relative_to(self.repo).parts
        if any(p in DENY_PARTS or DENY_NAMES.match(p) for p in parts):
            raise ToolError(f"{rel!r} is not readable through this tool")
        if candidate.suffix in DENY_SUFFIXES:
            raise ToolError(f"{rel!r} is not readable through this tool")
        return candidate

    def _journal(self, target_id: str, rel: str) -> None:
        self.journal.setdefault(target_id, set()).add(f"targets/{target_id}/{rel}")

    # ------------------------------------------------------------ tools

    def read_repository(self, path: str) -> dict[str, Any]:
        candidate = self._confine(path)
        rel = candidate.relative_to(self.repo).as_posix() if candidate != self.repo else "."
        top = rel.split("/", 1)[0]
        if rel != "." and top not in READ_ROOTS:
            raise ToolError(f"{path!r}: readable roots are {list(READ_ROOTS)}")
        if candidate.is_dir():
            entries = sorted(
                p.name + ("/" if p.is_dir() else "")
                for p in candidate.iterdir()
                if p.name not in DENY_PARTS and (rel != "." or p.name in READ_ROOTS)
            )
            return {
                "path": rel,
                "entries": entries[:MAX_LIST],
                "truncated": len(entries) > MAX_LIST,
            }
        if not candidate.is_file():
            raise ToolError(f"{path!r} does not exist")
        data = candidate.read_bytes()
        try:
            text = data[:MAX_READ].decode("utf-8")
        except UnicodeDecodeError:
            return {"path": rel, "binary": True, "size": len(data)}
        return {"path": rel, "content": text, "truncated": len(data) > MAX_READ, "size": len(data)}

    def inspect_target(self, target_id: str) -> dict[str, Any]:
        target = self._existing_target(target_id)
        out: dict[str, Any] = {
            "target_id": target_id,
            "files": sorted(
                p.relative_to(target).as_posix()
                for p in target.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts
            ),
            "fixtures": list(fixture_names(target)),
            "goldens": [g.name for g in golden_paths(target)],
            "surface": check_target(target),
            "completeness": completeness(target),
        }
        try:
            manifest = load_manifest(target / "manifest.yaml")
        except (ManifestSyntaxError, ValidationError, OSError) as exc:
            out["manifest"] = {"error": str(exc)}
            return out
        out["manifest"] = {
            "modality": manifest.modality,
            "dataset_id": manifest.contract.dataset_id,
            "metrics": list(manifest.contract.metrics),
            "allowed_hosts": list(manifest.allowed_hosts),
            "license": manifest.license,
        }
        out["validation"] = validate_manifest(manifest).model_dump(mode="json")
        return out

    def scaffold_target(
        self,
        target_id: str,
        modality: str,
        dataset_id: str | None = None,
        host: str | None = None,
        with_parser: bool = False,
    ) -> dict[str, Any]:
        self._target(target_id)
        if modality not in MODALITIES:
            raise ToolError(f"modality must be one of {list(MODALITIES)}")
        mod: Modality = modality  # narrowed by the check above
        try:
            result = scaffold_target(
                self.repo / "targets",
                target_id,
                mod,
                dataset_id=dataset_id,
                host=host or "replace-me.example",
                with_parser=bool(with_parser),
            )
        except ScaffoldError as exc:
            raise ToolError(str(exc)) from exc
        for path in result.files:
            self._journal(target_id, path.relative_to(result.target).as_posix())
        return {
            "target_id": target_id,
            "files": [p.relative_to(self.repo).as_posix() for p in result.files],
            "admission_required": result.admission_required,
            "next": f"fill every REPLACE_ME, then validate_target({target_id!r})",
        }

    def write_target_file(self, target_id: str, path: str, content: str) -> dict[str, Any]:
        target = self._existing_target(target_id)
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        if len(content.encode("utf-8")) > MAX_WRITE:
            raise ToolError(f"content exceeds {MAX_WRITE} bytes")
        if not isinstance(path, str) or not path or path.startswith(("/", "~")) or "\\" in path:
            raise ToolError(f"path must be relative to targets/{target_id}/: {path!r}")
        candidate = (target / path).resolve()
        if target != candidate and target not in candidate.parents:
            raise ToolError(f"{path!r} escapes targets/{target_id}/")
        if candidate.parts[len(target.parts) : len(target.parts) + 1] == ("fixtures",):
            raise ToolError("fixtures are written by record_fixture only (Bronze objects)")
        before = check_target(target)
        existed = candidate.exists()
        previous = candidate.read_bytes() if existed else None
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(content, encoding="utf-8")
        after = check_target(target)
        rel = candidate.relative_to(target).as_posix()
        new_problems = [p for p in after if p not in before and (rel in p or str(candidate) in p)]
        if new_problems:
            if previous is None:
                candidate.unlink()
                for parent in candidate.parents:
                    if parent == target:
                        break
                    if parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
            else:
                candidate.write_bytes(previous)
            raise ToolError(
                "write rejected by the surface rules (rolled back):\n  " + "\n  ".join(new_problems)
            )
        self._journal(target_id, rel)
        return {"written": f"targets/{target_id}/{rel}", "remaining_problems": after}

    def validate_target(self, target_id: str) -> dict[str, Any]:
        target = self._existing_target(target_id)
        surface = check_target(target)
        try:
            manifest = load_manifest(target / "manifest.yaml")
        except (ManifestSyntaxError, ValidationError, OSError) as exc:
            return {
                "target_id": target_id,
                "validation": {"status": "INVALID", "errors": [str(exc)]},
                "surface": surface,
            }
        result = validate_manifest(manifest)
        out: dict[str, Any] = {
            "target_id": target_id,
            "validation": result.model_dump(mode="json"),
            "surface": surface,
        }
        if result.status == "ADMISSION_REQUIRED":
            out["next"] = (
                "Route B (ADR-022): do not invent a unit or edit a registry; run "
                f"`energyctl admission-request {target_id}` and open a PR with only that file"
            )
        return out

    def record_fixture(
        self,
        target_id: str,
        name: str,
        payload_path: str | None = None,
        live: bool = False,
        scheduled_for: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        target = self._existing_target(target_id)
        if bool(live) == (payload_path is not None):
            raise ToolError("give exactly one of payload_path (offline) or live: true")
        try:
            manifest = load_manifest(target / "manifest.yaml")
        except (ManifestSyntaxError, ValidationError, OSError) as exc:
            raise ToolError(f"manifest: {exc}") from exc
        when = None
        if scheduled_for:
            when = datetime.fromisoformat(scheduled_for)
            if when.tzinfo is None:
                raise ToolError("scheduled_for must carry an offset (ADR-014)")
        try:
            if live:
                if not self.allow_network:
                    raise ToolError(
                        "network is not enabled for this server (start it with --allow-network, "
                        "or record from a saved payload)"
                    )
                fetcher = self.fetcher_factory() if self.fetcher_factory else None
                entry = record_live(target, manifest, name, scheduled_for=when, fetcher=fetcher)
            else:
                assert payload_path is not None
                entry = record_from_file(
                    target,
                    manifest,
                    name,
                    self._confine(payload_path),
                    scheduled_for=when,
                    content_type=content_type,
                )
        except (FixtureError, OSError) as exc:
            raise ToolError(f"record_fixture: {exc}") from exc
        self._journal(target_id, f"fixtures/{name}/entry.json")
        self._journal(target_id, f"fixtures/{name}/blob")
        return {
            "fixture": f"targets/{target_id}/fixtures/{name}",
            "entry": entry.model_dump(mode="json"),
        }

    def run_target_tests(self, target_id: str) -> dict[str, Any]:
        target = self._existing_target(target_id)
        report = run_target_tests(target)
        return {
            "target_id": target_id,
            "ok": report.ok,
            "lines": report.lines(),
            "pytest_output": report.pytest_output[-8000:],
        }

    def open_pr(
        self, target_id: str, title: str | None = None, body: str | None = None
    ) -> dict[str, Any]:
        self._existing_target(target_id)
        touched = sorted(p for paths in self.journal.values() for p in paths)
        if not touched:
            raise ToolError("nothing was written in this session; there is nothing to propose")
        try:
            bundle = prepare_bundle(
                self.repo,
                target_id,
                self.outbox,
                title=title,
                body=body or "",
                touched=tuple(touched),
            )
        except BundleRefused as exc:
            raise ToolError(str(exc)) from exc
        return {
            "bundle": str(bundle.path),
            "branch": bundle.branch,
            "files": list(bundle.files),
            "next": "a human or the CI bot runs `python -m scripts.apply_pr_bundle <bundle>` "
            "and `gh pr create`; this tool never pushes (ADR-006 Level 2)",
        }
