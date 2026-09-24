"""Egress policy gate: start a pod's work only once its NetworkPolicy is in force (05 C-65).

Some CNIs apply a new pod's policy asynchronously. On the demo's k3s (embedded kube-router) a
pod's first packets leave unfiltered for up to about a second: measured 2026-09-23, the
metadata service answered a fresh process pod with HTTP 200 and refused the same request 15 s
later. Cilium (kind) programs the policy before the pod runs. The chart can run this gate as an
init container (``egress.policyGate.enabled``).

Two canaries, two different signals (ADR-026 amendment 3, review 2 DEP-05):

* the **metadata canary** (``169.254.169.254:80``, denied to every role) must be *unreachable*
  twice in a row — the fail-closed check: a cluster that keeps answering it fails the pod after
  ``timeout``. Once the node itself blocks that address, this canary is unreachable whether or
  not the pod's policy exists, so it can no longer prove the policy;
* the **host canary** (the node's own address on a closed port, given by the chart from the
  downward API) tells the two apart: with no policy the node answers the SYN with a reset
  (``ConnectionRefusedError``); with the pod's egress policy in force the packet is dropped and
  the connect *times out*. The gate opens only when the host canary has been dropped twice in
  a row as well. A connect that succeeds or is refused means the policy is not there yet.

The main container, the one that handles source payloads, then starts under an enforced policy.
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
    """A canary stayed reachable (or the host canary kept answering) until the timeout; the pod
    must not start its work."""


@dataclass(frozen=True, slots=True)
class GateResult:
    waited_seconds: float
    attempts: int
    host_canary_dropped: bool | None = None
    """``True`` when the host canary timed out (dropped by the pod's policy); ``None`` when no
    host canary was given."""


def _tcp_connect(address: tuple[str, int], timeout: float) -> object:
    with socket.create_connection(address, timeout=timeout):
        return None


def _dropped(connect: Connect, address: tuple[str, int], timeout: float) -> bool:
    """Whether a connect to ``address`` was **dropped** (timed out or unreachable) rather than
    answered (connected) or refused (a reset: the node is there and no policy stands between)."""
    try:
        connect(address, timeout)
    except ConnectionRefusedError:
        return False
    except OSError:
        return True
    return False


def wait_for_egress_policy(
    *,
    canary: tuple[str, int] = CANARY,
    host_canary: tuple[str, int] | None = None,
    timeout: float = 60.0,
    blocked_in_a_row: int = 2,
    attempt_timeout: float = 0.5,
    interval: float = 0.25,
    connect: Connect = _tcp_connect,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> GateResult:
    """Return once ``blocked_in_a_row`` consecutive rounds found the metadata canary unreachable
    and (when given) the host canary dropped; raise :class:`PolicyNotEnforced` after
    ``timeout`` seconds otherwise."""
    start = clock()
    attempts = 0
    blocked = 0
    last_reason = "the metadata canary still answers"
    while True:
        attempts += 1
        try:
            connect(canary, attempt_timeout)
        except OSError:
            metadata_blocked = True
        else:
            metadata_blocked = False
        host_dropped = (
            True if host_canary is None else _dropped(connect, host_canary, attempt_timeout)
        )
        if metadata_blocked and host_dropped:
            blocked += 1
            if blocked >= blocked_in_a_row:
                return GateResult(
                    waited_seconds=clock() - start,
                    attempts=attempts,
                    host_canary_dropped=None if host_canary is None else True,
                )
        else:
            blocked = 0
            last_reason = (
                "the metadata canary still answers"
                if not metadata_blocked
                else "the host canary is answered or refused, not dropped: no egress policy "
                "stands between this pod and its node"
            )
        if clock() - start >= timeout:
            raise PolicyNotEnforced(
                f"after {timeout:.0f} s ({attempts} attempts) {last_reason}: the egress "
                f"NetworkPolicy is not enforced for this pod"
            )
        sleep(interval)
