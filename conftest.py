"""Repository-wide pytest configuration (ADR-027 §4, ADR-020, ADR-010).

Every test that is not marked ``live`` runs with the socket layer disabled, so a parser, a
fixture loader or a test that opens a network connection fails on the laptop and in CI without
any packet leaving the machine. ``make test`` selects ``-m "not live"``; the marker is the only
way to opt out, and only outside CI.

A target without a fixture, a golden or a test module fails the session before collection
(ADR-020; 05 C-14, C-15): the scaffold of ``energyctl new-target`` is not a target until it is
completed.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from energy_platform.harness.surface import incomplete_targets

pytest_plugins = ["pytester"]

_MSG = "network disabled in unit tests (ADR-027 §4); mark the test `live` if it must fetch"


def pytest_sessionstart(session: pytest.Session) -> None:
    problems = incomplete_targets(Path(session.config.rootpath) / "targets")
    if problems:
        raise pytest.UsageError(
            "incomplete target(s) fail collection (ADR-020):\n  " + "\n  ".join(problems)
        )


def _blocked(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError(_MSG)


class _BlockedSocket(socket.socket):
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(_MSG)


@pytest.fixture(autouse=True)
def _no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("live") is not None:
        yield
        return
    monkeypatch.setattr(socket, "socket", _BlockedSocket)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    yield
