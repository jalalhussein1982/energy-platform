"""Fail if uv.lock contains a package that is not in deps-allowlist.txt.

Mechanical form of the ADR-006 dependency gate: an agent or a junior may open a PR that adds a
package, but CI fails it until a human extends the allowlist (with an ADR, per ADR-019).
Transitive packages are listed too — slopsquatting (ADR-008) does not care who pulled a package in.

Usage: check_deps_allowlist.py <uv.lock> <deps-allowlist.txt>
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def lock_packages(lock_path: Path) -> set[str]:
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    names = {str(p["name"]).lower() for p in data.get("package", [])}
    # The project itself is in its own lockfile; it is not a dependency.
    project_name = _own_name()
    return names - {project_name}


def _own_name() -> str:
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data.get("project", {}).get("name", "")).lower()
    return ""


def allowlist(path: Path) -> set[str]:
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.add(line.lower())
    return names


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    lock, allow = Path(argv[1]), Path(argv[2])
    if not allow.exists():
        print(f"deps-allowlist: {allow} missing")
        return 1
    locked, allowed = lock_packages(lock), allowlist(allow)
    unlisted = sorted(locked - allowed)
    unused = sorted(allowed - locked)
    if unlisted:
        print("deps-allowlist: packages in uv.lock but NOT allowlisted (ADR first, then list):")
        for n in unlisted:
            print(f"  - {n}")
        return 1
    print(f"deps-allowlist: OK — {len(locked)} locked packages all allowlisted")
    if unused:
        joined = ", ".join(unused)
        print(f"deps-allowlist: note — {len(unused)} allowlisted but not locked: {joined}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
