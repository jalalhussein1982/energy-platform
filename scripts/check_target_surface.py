"""Enforce the target capability boundary (ADR-027 §1-§2) on every directory under targets/.

A target may contain only the files listed in ALLOWED; its parser may import only the platform
contracts package and a short list of pure-data standard-library modules; no file in a target may
carry a lint/type suppression or a test skip. Run by `make lint`; each rule has a negative test in
tests/harness/test_target_surface.py.

Usage: check_target_surface.py [targets-root]
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ALLOWED_TOP_FILES = {"__init__.py", "manifest.yaml", "parser.py", "README.md"}
ALLOWED_TEST_FILES = {"__init__.py"}
TEST_FILE = re.compile(r"^test_[a-z0-9_]+\.py$")
GOLDEN_FILE = re.compile(r"^[a-z0-9_.-]+\.ya?ml$")
TARGET_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

PARSER_STDLIB = {
    "decimal",
    "datetime",
    "zoneinfo",
    "re",
    "typing",
    "dataclasses",
    "collections",
    "enum",
    "itertools",
    "functools",
    "math",
    "fractions",
    "collections.abc",
}
PARSER_PLATFORM_PREFIX = "energy_platform.contracts"

FORBIDDEN_TOKENS: dict[str, re.Pattern[str]] = {
    "lint suppression": re.compile(r"#\s*noqa"),
    "type suppression": re.compile(r"#\s*type:\s*ignore"),
    "coverage/pragma suppression": re.compile(r"#\s*pragma"),
    "test skip": re.compile(r"pytest\.mark\.(skip|xfail)|pytest\.importorskip|pytest\.skip\("),
    "dynamic import": re.compile(r"__import__|importlib"),
    "code execution": re.compile(r"\b(exec|eval)\("),
    "file access": re.compile(r"\bopen\("),
    "builtins access": re.compile(r"__builtins__"),
}


def _classify(target: Path, path: Path) -> str | None:
    """Return None when the file is allowed, else the reason it is not."""
    rel = path.relative_to(target)
    parts = rel.parts
    if len(parts) == 1:
        return None if parts[0] in ALLOWED_TOP_FILES else "file outside the target surface"
    if parts[0] == "fixtures":
        return None
    if parts[0] == "tests":
        if len(parts) == 2:
            name = parts[1]
            if name in ALLOWED_TEST_FILES or TEST_FILE.match(name):
                return None
            if name == "conftest.py":
                return "conftest.py is not allowed in a target"
            return "file outside the target surface"
        if len(parts) == 3 and parts[1] == "golden" and GOLDEN_FILE.match(parts[2]):
            return None
        return "file outside the target surface"
    return "file outside the target surface"


def _check_parser_imports(path: Path) -> list[str]:
    problems: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append(f"{path}:{node.lineno}: relative import in parser")
                continue
            names = [node.module or ""]
        else:
            continue
        for name in names:
            ok = name in PARSER_STDLIB or name.startswith(PARSER_PLATFORM_PREFIX)
            if not ok:
                problems.append(f"{path}:{node.lineno}: import not allowed in a parser: {name}")
    return problems


def _check_tokens(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        for reason, pat in FORBIDDEN_TOKENS.items():
            if pat.search(line):
                problems.append(f"{path}:{lineno}: {reason}")
    return problems


def check_target(target: Path) -> list[str]:
    problems: list[str] = []
    if not TARGET_ID.match(target.name):
        problems.append(f"{target}: target id must match {TARGET_ID.pattern}")
    for path in sorted(p for p in target.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts:
            continue
        reason = _classify(target, path)
        if reason:
            problems.append(f"{path}: {reason}")
            continue
        if path.name == "__init__.py" and path.read_text(encoding="utf-8").strip():
            problems.append(f"{path}: __init__.py must be empty")
        if path.suffix == ".py":
            problems.extend(_check_tokens(path))
        if path.name == "parser.py":
            problems.extend(_check_parser_imports(path))
    return problems


def check_root(root: Path) -> list[str]:
    problems: list[str] = []
    for entry in sorted(root.iterdir()):
        if entry.name in {"__init__.py", "__pycache__"}:
            continue
        if not entry.is_dir():
            problems.append(f"{entry}: only target directories may live under {root}")
            continue
        problems.extend(check_target(entry))
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("targets")
    if not root.exists():
        print(f"target-surface: {root} missing")
        return 1
    problems = check_root(root)
    if problems:
        print("target-surface: violations of ADR-027:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("target-surface: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
