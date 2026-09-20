"""05 C-47…C-53: the MCP server exposes exactly the ADR-007 tools and its guards hold."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from energy_platform.mcp import TOOL_NAMES, Server, ToolError, Tools, serve
from energy_platform.mcp.tools import tool_definitions
from tests.harness.targets_builder import EXAMPLES, make_target

ADR_007 = {
    "read_repository",
    "inspect_target",
    "scaffold_target",
    "write_target_file",
    "validate_target",
    "record_fixture",
    "run_target_tests",
    "open_pr",
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "targets").mkdir(parents=True)
    (root / "targets" / "__init__.py").write_text("")
    (root / "docs").mkdir()
    (root / "docs" / "05-constraint-matrix.md").write_text("# 05\n")
    (root / "README.md").write_text("# repo\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n")
    (root / ".env").write_text("TOKEN=x\n")
    (root / "energy_platform").mkdir()
    (root / "energy_platform" / "secret_key.pem").write_text("-----BEGIN X-----\n")
    (root / "examples").mkdir()
    (root / "examples" / "payload.xml").write_bytes(
        (EXAMPLES / "fixtures" / "ote_idm_soap" / "blob").read_bytes()
    )
    return root


@pytest.fixture
def tools(repo: Path) -> Tools:
    return Tools(repo=repo, outbox=repo.parent / "outbox")


def _call(server: Server, name: str, **arguments: Any) -> dict[str, Any]:
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    result: dict[str, Any] = response["result"]
    return result


# ------------------------------------------------------------------ C-47 tool set


def test_tool_set_is_exactly_adr_007(tools: Tools) -> None:
    assert set(TOOL_NAMES) == ADR_007
    listed = {t["name"] for t in tool_definitions()}
    assert listed == ADR_007
    for name in ("run_shell", "kubectl", "terraform", "merge_pr", "write_file"):
        with pytest.raises(ToolError, match="unknown tool"):
            tools.call(name, {})
    server = Server(tools)
    listing = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listing is not None
    assert {t["name"] for t in listing["result"]["tools"]} == ADR_007
    for tool in listing["result"]["tools"]:
        assert tool["inputSchema"]["additionalProperties"] is False


def test_initialize_and_unknown_method(tools: Tools) -> None:
    server = Server(tools)
    init = server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    assert init is not None and init["result"]["serverInfo"]["name"] == "energy-platform"
    assert "ADMISSION_REQUIRED" in init["result"]["instructions"]
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    bad = server.handle({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
    assert bad is not None and bad["error"]["code"] == -32601
    ping = server.handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert ping is not None and ping["result"] == {}


# ------------------------------------------------------------------ C-52 reads


@pytest.mark.parametrize(
    "path",
    [
        "../",
        "/etc/passwd",
        ".git/config",
        ".env",
        "energy_platform/secret_key.pem",
        "docs/../.git/config",
        "~/x",
        "energy_platform/fetch/client.py",
    ],
)
def test_read_repository_confined(tools: Tools, path: str) -> None:
    with pytest.raises(ToolError):
        tools.read_repository(path)


def test_read_repository_lists_and_reads(tools: Tools) -> None:
    root = tools.read_repository(".")
    assert root["entries"] == ["README.md", "docs/", "examples/", "targets/"]
    assert ".git/" not in root["entries"] and ".env" not in root["entries"]
    assert tools.read_repository("docs/05-constraint-matrix.md")["content"] == "# 05\n"
    with pytest.raises(ToolError, match="does not exist"):
        tools.read_repository("docs/nope.md")


# ------------------------------------------------------------------ C-48, C-49 writes


def test_scaffold_then_write_and_inspect(tools: Tools) -> None:
    out = tools.scaffold_target(
        "probe_target", "soap-xml", dataset_id="ote.idm_continuous", host="www.ote-cr.cz"
    )
    assert out["admission_required"] is False
    written = tools.write_target_file("probe_target", "README.md", "# probe\n")
    assert written["written"] == "targets/probe_target/README.md"
    info = tools.inspect_target("probe_target")
    assert info["manifest"]["dataset_id"] == "ote.idm_continuous"
    assert any("placeholder" in p for p in info["surface"])
    assert any("no fixture" in p for p in info["completeness"])


@pytest.mark.parametrize(
    "path",
    [
        "../other_target/manifest.yaml",
        "/etc/passwd",
        "../../energy_platform/contracts/registry.py",
        "fetch.py",
        "tests/conftest.py",
        "tests/helpers.py",
        "fixtures/day/blob",
        "~/x",
    ],
)
def test_write_outside_surface_refused(tools: Tools, repo: Path, path: str) -> None:
    tools.scaffold_target("probe_target", "soap-xml")
    with pytest.raises(ToolError):
        tools.write_target_file("probe_target", path, "x = 1\n")
    assert not (repo / "targets" / "probe_target" / "fetch.py").exists()
    assert not (repo / "targets" / "other_target").exists()
    assert not (repo / "etc").exists()


def test_write_with_forbidden_content_is_rolled_back(tools: Tools, repo: Path) -> None:
    tools.scaffold_target("probe_target", "soap-xml", with_parser=True)
    parser = repo / "targets" / "probe_target" / "parser.py"
    before = parser.read_text()
    with pytest.raises(ToolError, match=r"import not allowed in a parser: http\.client"):
        tools.write_target_file("probe_target", "parser.py", "import http.client\n" + before)
    assert parser.read_text() == before  # previous content restored
    with pytest.raises(ToolError, match="hardcoded URL"):
        tools.write_target_file(
            "probe_target",
            "tests/test_extra.py",
            "URL = 'https://x.example'\n\ndef test_x() -> None:\n    assert URL\n",
        )
    assert not (repo / "targets" / "probe_target" / "tests" / "test_extra.py").exists()
    with pytest.raises(ToolError, match="lint suppression"):
        tools.write_target_file("probe_target", "tests/test_extra.py", "x = 1  # noqa\n")


def test_write_needs_an_existing_target(tools: Tools) -> None:
    with pytest.raises(ToolError, match="does not exist"):
        tools.write_target_file("ghost", "README.md", "x")


# ------------------------------------------------------------------ C-50 network opt-in


def test_record_fixture_live_needs_server_opt_in(tools: Tools) -> None:
    tools.scaffold_target("probe_target", "soap-xml")
    with pytest.raises(ToolError, match="allow-network"):
        tools.record_fixture("probe_target", "day", live=True)
    with pytest.raises(ToolError, match="exactly one"):
        tools.record_fixture("probe_target", "day")


def test_record_fixture_from_payload_is_offline(tools: Tools, repo: Path) -> None:
    make_target(repo / "targets", "ote_probe")
    out = tools.record_fixture(
        "ote_probe",
        "second_day",
        payload_path="examples/payload.xml",
        scheduled_for="2026-09-18T22:15:00+00:00",
    )
    assert out["entry"]["target_id"] == "ote_probe"
    assert (repo / "targets" / "ote_probe" / "fixtures" / "second_day" / "blob").is_file()
    with pytest.raises(ToolError, match="outside the repository"):
        tools.record_fixture("ote_probe", "third", payload_path="../outside.xml")


# ------------------------------------------------------------------ validate, tests, C-51 open_pr


def test_validate_target_points_to_route_b(tools: Tools, repo: Path) -> None:
    make_target(
        repo / "targets", "entsoe_probe", manifest=EXAMPLES / "manifests" / "entsoe_rest_xml.yaml"
    )
    out = tools.validate_target("entsoe_probe")
    assert out["validation"]["status"] == "ADMISSION_REQUIRED"
    assert "admission-request" in out["next"]


def test_run_target_tests_reports(tools: Tools, repo: Path) -> None:
    make_target(repo / "targets", "ote_probe")
    out = tools.run_target_tests("ote_probe")
    assert out["ok"] is True, out["lines"]


def test_open_pr_refuses_when_gates_are_red(tools: Tools, repo: Path) -> None:
    with pytest.raises(ToolError, match="does not exist"):
        tools.open_pr("probe_target")
    tools.scaffold_target("probe_target", "soap-xml")
    with pytest.raises(ToolError, match="gates are red"):
        tools.open_pr("probe_target")
    assert not tools.outbox.exists()


def test_open_pr_refuses_without_a_session_write(tools: Tools, repo: Path) -> None:
    make_target(repo / "targets", "ote_probe")
    with pytest.raises(ToolError, match="nothing was written"):
        tools.open_pr("ote_probe")


def test_open_pr_refuses_two_targets(tools: Tools, repo: Path) -> None:
    make_target(repo / "targets", "ote_probe")
    tools.write_target_file("ote_probe", "README.md", "# one\n")
    tools.scaffold_target("second_target", "soap-xml")
    with pytest.raises(ToolError, match="05 C-41"):
        tools.open_pr("ote_probe")


def test_open_pr_writes_a_bundle_and_never_pushes(tools: Tools, repo: Path) -> None:
    make_target(repo / "targets", "ote_probe")
    tools.write_target_file("ote_probe", "README.md", "# ote_probe\n\nchecked.\n")
    out = tools.open_pr("ote_probe", title="feat(target): ote_probe")
    bundle = json.loads(Path(out["bundle"]).read_text())
    assert bundle["branch"] == "target/ote_probe" and bundle["gates"]["ok"] is True
    assert all(f["path"].startswith("targets/ote_probe/") for f in bundle["files"])
    assert "never pushes" in out["next"]


# ------------------------------------------------------------------ transport


def test_stdio_loop_round_trip(tools: Tools, repo: Path) -> None:
    make_target(repo / "targets", "ote_probe")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "validate_target", "arguments": {"target_id": "ote_probe"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "read_repository", "arguments": {"path": ".git/config"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "validate_target", "arguments": {"nope": 1}},
        },
    ]
    stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\nnot json\n[]\n")
    stdout = io.StringIO()
    assert serve(Server(tools), stdin, stdout) == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [r["id"] for r in responses] == [1, 2, 3, 4, 5, None, None]
    validated = json.loads(responses[2]["result"]["content"][0]["text"])
    assert validated["validation"]["status"] == "OK"
    assert responses[3]["result"]["isError"] is True
    assert responses[4]["result"]["isError"] is True
    assert responses[5]["error"]["code"] == -32700 and responses[6]["error"]["code"] == -32600


def test_server_result_is_an_error_not_a_crash_for_guard_failures(tools: Tools) -> None:
    result = _call(Server(tools), "scaffold_target", target_id="Bad", modality="soap-xml")
    assert result["isError"] is True and "target id" in result["content"][0]["text"]
