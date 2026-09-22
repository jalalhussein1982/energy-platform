"""05 C-57: every pod the chart renders is restricted-PSS clean (A-14); one negative per rule."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from scripts.check_restricted_pss import check_documents

CLEAN: dict[str, Any] = {
    "apiVersion": "batch/v1",
    "kind": "CronJob",
    "metadata": {"name": "capture-ote"},
    "spec": {
        "schedule": "*/15 * * * *",
        "jobTemplate": {
            "spec": {
                "template": {
                    "spec": {
                        "securityContext": {
                            "runAsNonRoot": True,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "capture",
                                "image": "x@sha256:" + "a" * 64,
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                            }
                        ],
                    }
                }
            }
        },
    },
}
POD = ("spec", "jobTemplate", "spec", "template", "spec")


def _pod(doc: dict[str, Any]) -> dict[str, Any]:
    """The pod spec inside ``doc`` (the object itself, so mutations land in the document)."""
    node: Any = doc
    for key in POD:
        node = node[key]
    assert isinstance(node, dict)
    return node


def test_clean_pod_passes() -> None:
    assert check_documents([CLEAN]) == []


def test_non_pod_kinds_are_ignored() -> None:
    assert check_documents([{"kind": "ConfigMap", "metadata": {"name": "x"}}, "junk", None]) == []


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda p: p["securityContext"].pop("runAsNonRoot"), "runAsNonRoot"),
        (lambda p: p["securityContext"].pop("seccompProfile"), "seccompProfile"),
        (
            lambda p: p["containers"][0]["securityContext"].pop("allowPrivilegeEscalation"),
            "allowPrivilegeEscalation",
        ),
        (
            lambda p: p["containers"][0]["securityContext"].update(
                {"allowPrivilegeEscalation": True}
            ),
            "allowPrivilegeEscalation",
        ),
        (
            lambda p: p["containers"][0]["securityContext"].update(
                {"capabilities": {"drop": ["NET_RAW"]}}
            ),
            "capabilities.drop",
        ),
        (
            lambda p: p["containers"][0]["securityContext"].update(
                {"capabilities": {"drop": ["ALL"], "add": ["SYS_ADMIN"]}}
            ),
            "capabilities.add",
        ),
        (
            lambda p: p["containers"][0]["securityContext"].update({"privileged": True}),
            "privileged",
        ),
        (lambda p: p.update({"hostNetwork": True}), "hostNetwork"),
        (lambda p: p.update({"hostPID": True}), "hostPID"),
        (lambda p: p.update({"volumes": [{"name": "h", "hostPath": {"path": "/"}}]}), "hostPath"),
        (
            lambda p: p["containers"][0].update({"ports": [{"containerPort": 80, "hostPort": 80}]}),
            "hostPort",
        ),
    ],
)
def test_each_restricted_rule_is_enforced(mutate: Any, fragment: str) -> None:
    doc = deepcopy(CLEAN)
    mutate(_pod(doc))
    problems = check_documents([doc])
    assert problems and all("CronJob/capture-ote" in p for p in problems)
    assert any(fragment in p for p in problems), problems


def test_init_containers_are_checked_too() -> None:
    doc = deepcopy(CLEAN)
    _pod(doc)["initContainers"] = [{"name": "init", "image": "x@sha256:" + "b" * 64}]
    problems = check_documents([doc])
    assert any("container init" in p and "allowPrivilegeEscalation" in p for p in problems)


def test_container_level_settings_may_replace_pod_level_ones() -> None:
    doc = deepcopy(CLEAN)
    pod = _pod(doc)
    pod.pop("securityContext")
    pod["containers"][0]["securityContext"].update(
        {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}}
    )
    assert check_documents([doc]) == []
