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


HOST = ("10.0.0.5", 9)


def two_canaries(metadata: list[bool], host: list[str]) -> Connect:
    """``metadata``: True = answers; ``host``: "refused" | "dropped" | "open" per attempt."""

    def connect(address: tuple[str, int], timeout: float) -> object:
        if address == CANARY:
            if metadata.pop(0) if metadata else False:
                return None
            raise ConnectionRefusedError("refused")
        outcome = host.pop(0) if host else "dropped"
        if outcome == "refused":
            raise ConnectionRefusedError("reset by the node: no policy in between")
        if outcome == "dropped":
            raise TimeoutError("timed out: dropped by the pod's policy")
        return None

    return connect


def test_host_canary_refused_means_no_policy_even_when_metadata_is_blocked_by_the_node() -> None:
    """ADR-026 amendment 3 (review 2 DEP-05): after the node-level metadata block the metadata
    canary is unreachable from the first attempt; only a *dropped* host canary proves the pod's
    own policy. Refused twice, then dropped twice → opens on the fourth attempt."""
    clock = Clock()
    connect = two_canaries([False] * 8, ["refused", "refused", "dropped", "dropped"])
    result = wait_for_egress_policy(
        host_canary=HOST, connect=connect, clock=clock, sleep=clock.sleep
    )
    assert result.attempts == 4 and result.host_canary_dropped is True


def test_host_canary_that_keeps_answering_fails_closed() -> None:
    clock = Clock()
    connect = two_canaries([False] * 100, ["open"] * 100)
    with pytest.raises(PolicyNotEnforced, match="host canary"):
        wait_for_egress_policy(
            host_canary=HOST, timeout=5.0, connect=connect, clock=clock, sleep=clock.sleep
        )


def test_without_a_host_canary_the_metadata_rule_stands_alone() -> None:
    clock = Clock()
    connect, _ = connector([False, False])
    result = wait_for_egress_policy(connect=connect, clock=clock, sleep=clock.sleep)
    assert result.host_canary_dropped is None
