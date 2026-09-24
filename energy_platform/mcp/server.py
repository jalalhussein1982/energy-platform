"""JSON-RPC 2.0 over stdio, the MCP subset eight tools need (P3-D1).

Methods: ``initialize``, ``notifications/initialized`` (ignored), ``ping``, ``tools/list``,
``tools/call``. One JSON message per line on stdin/stdout; nothing else is written to stdout.
Errors from a guard come back as a tool result with ``isError: true`` so the agent can read the
reason; protocol errors use JSON-RPC error objects. No network, no threads, no dependency.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

import energy_platform
from energy_platform.mcp.tools import ToolError, Tools, tool_definitions

PROTOCOL_VERSION = "2025-06-18"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


class Server:
    def __init__(self, tools: Tools) -> None:
        self.tools = tools
        self.initialized = False

    # ------------------------------------------------------------ protocol

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """One request → one response; notifications return None."""
        if message.get("jsonrpc") != "2.0" or "method" not in message:
            return _error(message.get("id"), INVALID_REQUEST, "not a JSON-RPC 2.0 request")
        method = message["method"]
        params = message.get("params") or {}
        msg_id = message.get("id")
        if method.startswith("notifications/"):
            if method == "notifications/initialized":
                self.initialized = True
            return None
        if method == "initialize":
            return _result(msg_id, self._initialize())
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": tool_definitions()})
        if method == "tools/call":
            return self._call(msg_id, params)
        return _error(msg_id, METHOD_NOT_FOUND, f"unknown method {method!r}")

    def _initialize(self) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "energy-platform", "version": energy_platform.__version__},
            "instructions": (
                "Golden path (ADR-007): scaffold_target → write_target_file (manifest, goldens) → "
                "record_fixture → validate_target → run_target_tests → open_pr. A target touches "
                "only targets/<id>/. ADMISSION_REQUIRED means stop and call admission_request "
                "(Route B: the document goes to the outbox for a human to file); never invent a "
                "unit or edit a registry."
            ),
        }

    def _call(self, msg_id: Any, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _error(msg_id, INVALID_PARAMS, "tools/call needs name and arguments")
        try:
            payload = self.tools.call(name, arguments)
        except ToolError as exc:
            return _result(msg_id, _content(str(exc), is_error=True))
        except TypeError as exc:  # wrong argument names/arity
            return _result(msg_id, _content(f"invalid arguments: {exc}", is_error=True))
        return _result(msg_id, _content(json.dumps(payload, indent=2, default=str)))


def _content(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def serve(server: Server, stdin: TextIO, stdout: TextIO) -> int:
    """Line-delimited JSON-RPC until EOF. Returns the exit code."""
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response: dict[str, Any] | None = _error(None, PARSE_ERROR, "invalid JSON")
        else:
            response = (
                server.handle(message)
                if isinstance(message, dict)
                else _error(None, INVALID_REQUEST, "batch requests are not supported")
            )
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


def serve_stdio(repo: Path, outbox: Path, *, allow_network: bool = False) -> int:
    tools = Tools(repo=repo, outbox=outbox, allow_network=allow_network)
    return serve(Server(tools), sys.stdin, sys.stdout)
