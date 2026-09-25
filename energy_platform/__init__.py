"""energy_platform — the one library behind energyctl, the MCP server and CI (ADR-000).

Semantics live here: fetch, bronze, parse, mapping, silver, ledger. Targets contribute
syntax only (manifest, optional parser, fixtures, goldens) — see ADR-005.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

__version__ = "0.0.1"


@lru_cache(maxsize=4)
def source_digest(root: Path | None = None) -> str:
    """First 12 hex of SHA-256 over every ``.py`` file of the package (relative path and
    bytes, sorted): the identity of the implementation, the same on a laptop and in the image
    (which copies the same files), different after any code change. Bytecode does not count."""
    base = root if root is not None else Path(__file__).resolve().parent
    h = hashlib.sha256()
    for path in sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts):
        h.update(path.relative_to(base).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:12]


def implementation_version() -> str:
    """ADR-023 amendment 3: the package version plus the source digest — the
    ``platform_version`` component of every derivation identity. A parser or mapping fix is a
    new derivation whether or not anyone bumps ``__version__``."""
    return f"{__version__}+{source_digest()}"
