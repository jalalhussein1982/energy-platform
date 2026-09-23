"""Egress policy gate: start a pod's work only once its NetworkPolicy is in force (05 C-65).

Some CNIs apply a new pod's policy asynchronously. On the demo's k3s (embedded kube-router) a
pod's first packets leave unfiltered for up to about a second: measured 2026-09-23, the
metadata service answered a fresh process pod with HTTP 200 and refused the same request 15 s
later. Cilium (kind) programs the policy before the pod runs. The chart can run this gate as an
init container (``egress.policyGate.enabled``). It waits until a TCP connect to a canary that
every role's policy denies, the link-local metadata address on port 80, fails twice in a row.
The main container, the one that handles source payloads, then starts under an enforced policy.
A cluster that never blocks the canary fails the pod after ``timeout``: fail closed.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass

CANARY = ("169.254.169.254", 80)
"""Denied to every platform role (the metadata address is in every ``except`` list)."""

Connect = Callable[[tuple[str, int], float], object]


class PolicyNotEnforced(RuntimeError):
    """The canary stayed reachable until the timeout; the pod must not start its work."""


@dataclass(frozen=True, slots=True)
class GateResult:
    waited_seconds: float
    attempts: int


def _tcp_connect(address: tuple[str, int], timeout: float) -> object:
    with socket.create_connection(address, timeout=timeout):
        return None


def wait_for_egress_policy(
    *,
    canary: tuple[str, int] = CANARY,
    timeout: float = 60.0,
    blocked_in_a_row: int = 2,
    attempt_timeout: float = 0.5,
    interval: float = 0.25,
    connect: Connect = _tcp_connect,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> GateResult:
    """Return once ``blocked_in_a_row`` consecutive connects to ``canary`` fail; raise
    :class:`PolicyNotEnforced` if it is still reachable after ``timeout`` seconds."""
    start = clock()
    attempts = 0
    blocked = 0
    while True:
        attempts += 1
        try:
            connect(canary, attempt_timeout)
        except OSError:
            blocked += 1
            if blocked >= blocked_in_a_row:
                return GateResult(waited_seconds=clock() - start, attempts=attempts)
        else:
            blocked = 0
        if clock() - start >= timeout:
            raise PolicyNotEnforced(
                f"{canary[0]}:{canary[1]} still reachable after {timeout:.0f} s "
                f"({attempts} attempts): the egress NetworkPolicy is not enforced for this pod"
            )
        sleep(interval)
