"""Enforce the target capability boundary (ADR-027 §1-§2) on every directory under targets/.

Thin wrapper: the rules live in ``energy_platform.harness.surface`` so that ``energyctl`` and the
MCP server apply exactly what CI applies. Run by ``make lint``; each rule has a negative test in
``tests/harness/test_target_surface.py``.

Usage: check_target_surface.py [targets-root]
"""

from __future__ import annotations

import sys
from pathlib import Path

from energy_platform.harness.surface import report


def main(argv: list[str]) -> int:
    code, lines = report(Path(argv[1]) if len(argv) > 1 else Path("targets"))
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
