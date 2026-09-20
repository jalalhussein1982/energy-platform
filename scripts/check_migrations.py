"""Every migration has a real downgrade and the revision chain is linear (ADR-016 §3; 05 C-45).

Static complement of ``make db-test`` (which runs upgrade → downgrade → upgrade on PostgreSQL):
a migration whose ``downgrade()`` is missing, ``pass``, ``...`` or ``raise NotImplementedError``
fails here without a database.

Usage: check_migrations.py [versions-dir]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

DEFAULT_DIR = Path("energy_platform/silver/migrations/versions")


def _is_placeholder(fn: ast.FunctionDef) -> bool:
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # docstring
    if not body:
        return True
    if all(isinstance(n, ast.Pass) for n in body):
        return True
    if len(body) == 1:
        node = body[0]
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            return True  # `...`
        if isinstance(node, ast.Raise):
            exc = node.exc
            name = (
                exc.id
                if isinstance(exc, ast.Name)
                else exc.func.id
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
                else ""
            )
            if name == "NotImplementedError":
                return True
    return False


def _assigned(tree: ast.Module, name: str) -> tuple[bool, object]:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (
                    isinstance(t, ast.Name)
                    and t.id == name
                    and isinstance(node.value, ast.Constant)
                ):
                    return True, node.value.value
    return False, None


def check_migration_text(
    text: str, source: str = "migration.py"
) -> tuple[list[str], str | None, object]:
    """Problems, revision id, down_revision for one migration module."""
    try:
        tree = ast.parse(text, filename=source)
    except SyntaxError as exc:
        return [f"{source}: syntax error: {exc.msg}"], None, None
    problems: list[str] = []
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "upgrade" not in fns:
        problems.append(f"{source}: no upgrade()")
    if "downgrade" not in fns:
        problems.append(f"{source}: no downgrade() (ADR-016 §3; 05 C-45)")
    elif _is_placeholder(fns["downgrade"]):
        problems.append(f"{source}: downgrade() is a placeholder, not a downgrade (05 C-45)")
    has_rev, rev = _assigned(tree, "revision")
    has_down, down = _assigned(tree, "down_revision")
    if not has_rev or not isinstance(rev, str):
        problems.append(f"{source}: no `revision` string")
    if not has_down:
        problems.append(f"{source}: no `down_revision`")
    return problems, rev if isinstance(rev, str) else None, down


def check_directory(directory: Path) -> list[str]:
    files = sorted(p for p in directory.glob("*.py") if p.name != "__init__.py")
    if not files:
        return [f"{directory}: no migrations found"]
    problems: list[str] = []
    revisions: dict[str, object] = {}
    for path in files:
        found, rev, down = check_migration_text(path.read_text(encoding="utf-8"), str(path))
        problems.extend(found)
        if rev is not None:
            if rev in revisions:
                problems.append(f"{path}: duplicate revision {rev!r}")
            revisions[rev] = down
    downs = [d for d in revisions.values() if d is not None]
    for d in downs:
        if d not in revisions:
            problems.append(f"down_revision {d!r} does not exist")
    roots = [r for r, d in revisions.items() if d is None]
    heads = [r for r in revisions if r not in downs]
    if len(roots) != 1:
        problems.append(f"expected one root migration, found {roots}")
    if len(heads) != 1:
        problems.append(f"expected one head migration, found {heads} (linear chain, ADR-016 §3)")
    return problems


def main(argv: list[str]) -> int:
    directory = Path(argv[1]) if len(argv) > 1 else DEFAULT_DIR
    if not directory.is_dir():
        print(f"migration-check: {directory} missing")
        return 1
    problems = check_directory(directory)
    if problems:
        print("migration-check: violations (ADR-016 §3):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("migration-check: OK — every migration has a downgrade; chain is linear")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
