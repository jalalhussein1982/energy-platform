"""05 C-65: the egress policy gate (fake connector and clock; no socket is opened)."""

from __future__ import annotations

from pathlib import Path

import pytest

from energy_platform.fetch.policy_gate import (
    CANARY,
    Connect,
    PolicyNotEnforced,
    dns_metrics_canary,
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


DNS = ("10.43.0.10", 9153)


CONTROL = ("10.43.0.10", 53)


def two_canaries(metadata: list[bool], policy: list[str], control_up: bool = True) -> Connect:
    """``metadata``: True = answers; ``policy``: "refused" | "dropped" | "open" per attempt on
    the metrics port; the control port 53 answers unless ``control_up`` is False."""

    def connect(address: tuple[str, int], timeout: float) -> object:
        if address == CANARY:
            if metadata.pop(0) if metadata else False:
                return None
            raise ConnectionRefusedError("refused")
        if address == CONTROL:
            if control_up:
                return None
            raise TimeoutError("DNS service unreachable")
        outcome = policy.pop(0) if policy else "dropped"
        if outcome == "refused":
            raise ConnectionRefusedError("kube-router rejects denied traffic with an ICMP error")
        if outcome == "dropped":
            raise TimeoutError("timed out: dropped by the pod's policy (Cilium, a firewall)")
        return None

    return connect


def test_policy_canary_answered_means_no_policy_even_when_the_node_blocks_metadata() -> None:
    """ADR-026 amendment 3 (review 2 DEP-05): after the node-level metadata block the metadata
    canary is unreachable from the first attempt; only a *denied* policy canary (CoreDNS's
    metrics port, which accepts without the policy) proves the pod's own policy — refused on
    kube-router, dropped on Cilium, both count. Open twice, then denied twice → opens on the
    fourth attempt."""
    clock = Clock()
    connect = two_canaries([False] * 8, ["open", "open", "refused", "dropped"])
    result = wait_for_egress_policy(
        policy_canary=DNS, connect=connect, clock=clock, sleep=clock.sleep
    )
    assert result.attempts == 4 and result.policy_canary_denied is True


def test_policy_canary_that_keeps_answering_fails_closed() -> None:
    clock = Clock()
    connect = two_canaries([False] * 100, ["open"] * 100)
    with pytest.raises(PolicyNotEnforced, match="policy canary"):
        wait_for_egress_policy(
            policy_canary=DNS, timeout=5.0, connect=connect, clock=clock, sleep=clock.sleep
        )


def test_an_unreachable_dns_service_keeps_the_gate_closed() -> None:
    """A denied canary proves nothing when its control port does not answer either: the DNS
    service may be down or unrouted; the gate fails closed instead of opening blindly."""
    clock = Clock()
    connect = two_canaries([False] * 100, ["refused"] * 100, control_up=False)
    with pytest.raises(PolicyNotEnforced, match="control port 53"):
        wait_for_egress_policy(
            policy_canary=DNS, timeout=5.0, connect=connect, clock=clock, sleep=clock.sleep
        )


def test_without_a_policy_canary_the_metadata_rule_stands_alone() -> None:
    clock = Clock()
    connect, _ = connector([False, False])
    result = wait_for_egress_policy(connect=connect, clock=clock, sleep=clock.sleep)
    assert result.policy_canary_denied is None


def test_dns_metrics_canary_comes_from_resolv_conf(tmp_path: Path) -> None:
    resolv = tmp_path / "resolv.conf"
    resolv.write_text(
        "search energy-platform.svc.cluster.local\nnameserver 10.43.0.10\noptions ndots:5\n"
    )
    assert dns_metrics_canary(9153, str(resolv)) == ("10.43.0.10", 9153)
    resolv.write_text("options ndots:5\n")
    assert dns_metrics_canary(9153, str(resolv)) is None
    assert dns_metrics_canary(9153, str(tmp_path / "missing")) is None
