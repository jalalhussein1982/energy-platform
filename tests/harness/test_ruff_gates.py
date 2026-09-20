"""05 C-08, C-09, C-30: the ruff rules of pyproject.toml, proven on planted snippets.

ruff runs as a subprocess with the repository configuration and `--stdin-filename`, so the
per-file exemptions apply exactly as in `make lint`. `tests/harness/` is the one test directory
where TID251 is relaxed, for this purpose.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def ruff_codes(snippet: str, filename: str) -> set[str]:
    exe = shutil.which("ruff")
    argv = [exe] if exe else [sys.executable, "-m", "ruff"]
    result = subprocess.run(  # noqa: S603 — fixed argv, snippet on stdin
        [
            *argv,
            "check",
            "--config",
            str(REPO / "pyproject.toml"),
            "--stdin-filename",
            filename,
            "--output-format",
            "json",
            "--no-cache",
            "-",
        ],
        input=snippet,
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    return {item["code"] for item in json.loads(result.stdout or "[]")}


# ------------------------------------------------------------------ C-30 egress outside fetch/


@pytest.mark.parametrize(
    "line",
    [
        "import httpx",
        "import requests",
        "import urllib.request",
        "import http.client",
        "import socket",
        "import subprocess",
        "import importlib",
        "from urllib3 import PoolManager",
    ],
)
@pytest.mark.parametrize(
    "filename", ["energy_platform/mapping/probe.py", "energy_platform/runtime/probe.py"]
)
def test_http_client_outside_fetch_rejected(line: str, filename: str) -> None:
    assert "TID251" in ruff_codes(f"{line}\n\nx = 1\n", filename)


def test_fetch_package_is_the_only_exemption() -> None:
    codes = ruff_codes(
        "import httpx\n\nclient = httpx.Client()\n", "energy_platform/fetch/probe.py"
    )
    assert "TID251" not in codes
    codes = ruff_codes(
        "import httpx\n\nclient = httpx.Client()\n", "energy_platform/bronze/probe.py"
    )
    assert "TID251" in codes


# ------------------------------------------------------------------ C-08 swallowed exception


@pytest.mark.parametrize(
    ("snippet", "code"),
    [
        ("try:\n    x = 1\nexcept Exception:\n    pass\n", "S110"),
        ("try:\n    x = 1\nexcept:\n    x = 2\n", "E722"),
        ("try:\n    x = 1\nexcept Exception:\n    x = 2\n", "BLE001"),
        ("try:\n    x = 1\nexcept BaseException:\n    x = 2\n", "BLE001"),
    ],
)
def test_swallowed_exception_rejected(snippet: str, code: str) -> None:
    assert code in ruff_codes(snippet, "energy_platform/mapping/probe.py")


def test_narrow_except_is_fine() -> None:
    snippet = "try:\n    x = 1\nexcept ValueError:\n    x = 2\n"
    assert not {"S110", "E722", "BLE001"} & ruff_codes(snippet, "energy_platform/mapping/probe.py")


# ------------------------------------------------------------------ C-09 naive datetime


@pytest.mark.parametrize(
    "snippet",
    [
        "from datetime import datetime\n\nnow = datetime.now()\n",
        "from datetime import datetime\n\nnow = datetime.utcnow()\n",
        "from datetime import datetime\n\nd = datetime(2026, 1, 1)\n",
        "from datetime import datetime\n\nd = datetime.fromtimestamp(0)\n",
        "import datetime\n\nd = datetime.datetime.utcfromtimestamp(0)\n",
    ],
)
@pytest.mark.parametrize("filename", ["energy_platform/mapping/probe.py", "targets/x/parser.py"])
def test_naive_datetime_rejected(snippet: str, filename: str) -> None:
    codes = ruff_codes(snippet, filename)
    assert codes & {"DTZ001", "DTZ003", "DTZ005", "DTZ006", "TID251"}, codes


def test_aware_datetime_is_fine() -> None:
    snippet = "from datetime import UTC, datetime\n\nnow = datetime.now(tz=UTC)\n"
    assert not {
        c for c in ruff_codes(snippet, "energy_platform/mapping/probe.py") if c.startswith("DTZ")
    }
