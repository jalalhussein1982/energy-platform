"""ADR-027 §4: a unit test cannot open a socket; a `live` test can (F03 runtime block)."""

from __future__ import annotations

import socket

import pytest


def test_socket_constructor_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="ADR-027"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_create_connection_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="ADR-027"):
        socket.create_connection(("127.0.0.1", 9), timeout=0.01)


def test_name_resolution_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="ADR-027"):
        socket.getaddrinfo("localhost", 80)


@pytest.mark.live
def test_live_marker_opts_out() -> None:
    # Never selected by `make test`; documents the opt-out without contacting anything.
    assert socket.socket is not None
