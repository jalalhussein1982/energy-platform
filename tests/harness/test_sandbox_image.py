"""05 C-67: the constrained-agent sandbox image (ADR-007 mode 2, `deployment/sandbox/`).

The threat model (§13) recorded that no test asserted the image's contents. These checks read the
Dockerfile, so they run offline in `make test`. They prove what the build does, not what a
registry serves: building the image and probing it for a shell is `docker run --entrypoint
/bin/sh …` (it must fail), which needs Docker and is not part of the offline gate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "deployment" / "sandbox" / "Dockerfile"


def _instructions() -> list[tuple[str, str]]:
    """(INSTRUCTION, argument) pairs with line continuations joined and comments dropped."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    logical: list[str] = []
    buf = ""
    for line in text.splitlines():
        if line.lstrip().startswith("#") or not line.strip():
            continue
        buf += line.rstrip("\\").rstrip() + " "
        if not line.rstrip().endswith("\\"):
            logical.append(buf.strip())
            buf = ""
    out = []
    for item in logical:
        word, _, arg = item.partition(" ")
        out.append((word.upper(), arg.strip()))
    return out


def _final_stage() -> list[tuple[str, str]]:
    ins = _instructions()
    last_from = max(i for i, (w, _) in enumerate(ins) if w == "FROM")
    return ins[last_from:]


def test_every_base_image_is_pinned_by_digest() -> None:
    froms = [arg for w, arg in _instructions() if w == "FROM"]
    assert froms and all(re.search(r"@sha256:[0-9a-f]{64}", f) for f in froms), froms


def test_the_final_image_removes_every_shell_and_the_installer() -> None:
    runs = " ".join(arg for w, arg in _final_stage() if w == "RUN")
    for path in (
        "/bin/sh",
        "/bin/bash",
        "/bin/dash",
        "/usr/bin/sh",
        "/usr/bin/bash",
        "/usr/bin/dash",
    ):
        assert re.search(rf"rm -f[^&]*\s{re.escape(path)}(\s|$)", runs), f"{path} not removed"
    assert "rm -f /usr/local/bin/uv" in runs  # no package installer left behind


def test_no_operator_tool_or_credential_is_installed() -> None:
    final = " ".join(arg for _, arg in _final_stage()).lower()
    for tool in ("kubectl", "terraform", "tofu", "helm", "git ", "openssh", "curl", "wget", "aws"):
        assert tool not in final, tool
    assert not [
        arg
        for w, arg in _final_stage()
        if w in {"ENV", "ARG"} and re.search(r"(token|secret|password|key)\s*=", arg, re.IGNORECASE)
    ]


def test_runs_unprivileged_with_the_mcp_server_as_the_only_entrypoint() -> None:
    final = _final_stage()
    users = [arg for w, arg in final if w == "USER"]
    assert users == ["agent:agent"]
    assert "--uid 10001" in " ".join(arg for w, arg in final if w == "RUN")
    entry = [arg for w, arg in final if w == "ENTRYPOINT"]
    assert len(entry) == 1
    argv = json.loads(entry[0])  # exec form: no shell to interpret it
    assert argv[:4] == ["/app/.venv/bin/python", "-m", "energy_platform.cli", "mcp-serve"]
    assert "--allow-network" not in argv  # live fixtures are opted into per session
    assert not [w for w, _ in final if w in {"CMD", "SHELL"}]
