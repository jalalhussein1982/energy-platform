"""The harness: the library behind ``energyctl``, the MCP server and the CI gates (ADR-007).

Everything that constrains target-writing lives here once and is called from three places:
the CLI (developer mode), the MCP server (constrained-agent mode) and ``scripts/check_*.py``
(CI). ``docs/05-constraint-matrix.md`` maps every failure mode to the function that rejects it.
"""

from energy_platform.harness.surface import (
    check_root,
    check_target,
    completeness,
    incomplete_targets,
)

__all__ = ["check_root", "check_target", "completeness", "incomplete_targets"]
