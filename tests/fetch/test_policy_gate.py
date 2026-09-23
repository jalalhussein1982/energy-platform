"""05 C-65: the egress policy gate (fake connector and clock; no socket is opened)."""

from __future__ import annotations

import pytest

from energy_platform.fetch.policy_gate import (
    CANARY,
    Connect,
    PolicyNotEnforced,
    wait_for_egress_policy,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def connector(outcomes: list[bool]) -> tuple[Connect, list[tuple[str, int]]]:
    """True = the canary answered (policy not yet enforced); False = refused or timed out."""
    seen: list[tuple[str, int]] = []

    def connect(address: tuple[str, int], timeout: float) -> object:
        seen.append(address)
        if outcomes.pop(0) if outcomes else True:
            return None
        raise ConnectionRefusedError("refused")

    return connect, seen


def test_gate_waits_through_the_unfiltered_start_then_opens() -> None:
    # the demo's kube-router: the first packets pass, then the pod's policy lands
    clock = Clock()
    connect, seen = connector([True, True, True, False, False])
    result = wait_for_egress_policy(connect=connect, clock=clock, sleep=clock.sleep)
    assert (result.attempts, len(seen)) == (5, 5)
    assert set(seen) == {CANARY}


def test_one_blocked_attempt_between_answers_is_not_enough() -> None:
    clock = Clock()
    connect, _ = connector([False, True, False, False])
    assert wait_for_egress_policy(connect=connect, clock=clock, sleep=clock.sleep).attempts == 4


def test_a_cluster_that_never_blocks_the_canary_fails_closed() -> None:
    clock = Clock()
    connect, _ = connector([])  # answers forever
    with pytest.raises(PolicyNotEnforced, match="not enforced"):
        wait_for_egress_policy(timeout=5.0, connect=connect, clock=clock, sleep=clock.sleep)
    assert clock.now >= 5.0


def test_already_enforced_opens_at_once() -> None:
    clock = Clock()
    connect, _ = connector([False, False])
    result = wait_for_egress_policy(connect=connect, clock=clock, sleep=clock.sleep)
    assert result.attempts == 2
