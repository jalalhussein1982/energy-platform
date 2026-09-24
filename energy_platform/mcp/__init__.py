"""MCP server: the ADR-007 tool set as thin wrappers over ``energy_platform.harness``.

``read_repository``, ``inspect_target``, ``scaffold_target``, ``write_target_file``,
``validate_target``, ``record_fixture``, ``run_target_tests``, ``admission_request`` (Route B,
added 2026-09-24 for review 2 AE-04), ``open_pr`` — nothing else (05 C-47). The transport is
JSON-RPC 2.0 over stdio on the standard library (P3-D1). In developer mode CI is the
enforcement; in constrained-agent mode the sandbox around this process is the boundary (ADR-007,
ADR-027 §5) and the guards in :mod:`tools` are what the agent sees.
"""

from energy_platform.mcp.server import Server, serve, serve_stdio
from energy_platform.mcp.tools import TOOL_NAMES, ToolError, Tools

__all__ = ["TOOL_NAMES", "Server", "ToolError", "Tools", "serve", "serve_stdio"]
