"""05 C-42…C-44: action pins, image digests, requests/limits (A-8, ADR-016 §1)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts.check_workloads import (
    check_dockerfile,
    check_k8s_documents,
    check_workflow,
    scan,
)

DIGEST = "sha256:" + "a" * 64
REPO = Path(__file__).resolve().parents[2]


def _cronjob(image: str, resources: Mapping[str, Any] | None) -> dict[str, object]:
    container: dict[str, object] = {"name": "capture", "image": image}
    if resources is not None:
        container["resources"] = resources
    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {"name": "capture-ote"},
        "spec": {
            "schedule": "*/15 * * * *",
            "jobTemplate": {"spec": {"template": {"spec": {"containers": [container]}}}},
        },
    }


FULL = {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "1", "memory": "512Mi"}}


def test_control_cronjob_passes() -> None:
    assert check_k8s_documents([_cronjob(f"ghcr.io/x/energy-platform@{DIGEST}", FULL)]) == []


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/x/energy-platform:latest",
        "ghcr.io/x/energy-platform:1.2.3",
        "energy-platform",
        "ghcr.io/x/energy-platform@sha256:abc",
    ],
)
def test_mutable_image_tag_rejected(image: str) -> None:
    problems = check_k8s_documents([_cronjob(image, FULL)])
    assert any("05 C-43" in p for p in problems), problems


def test_container_without_requests_rejected() -> None:
    problems = check_k8s_documents(
        [_cronjob(f"x@{DIGEST}", {"limits": {"cpu": "1", "memory": "512Mi"}})]
    )
    assert {p for p in problems if "requests" in p}, problems
    assert any("resources.requests.cpu missing (A-8; 05 C-44)" in p for p in problems)


def test_container_without_limits_rejected() -> None:
    problems = check_k8s_documents(
        [_cronjob(f"x@{DIGEST}", {"requests": {"cpu": "1", "memory": "512Mi"}})]
    )
    assert any("resources.limits.memory missing" in p for p in problems), problems


def test_container_without_any_resources_rejected() -> None:
    problems = check_k8s_documents([_cronjob(f"x@{DIGEST}", None)])
    assert len([p for p in problems if "05 C-44" in p]) == 4


def test_init_containers_and_deployments_are_checked() -> None:
    doc = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "api"},
        "spec": {
            "template": {
                "spec": {
                    "initContainers": [{"name": "migrate", "image": "x:latest"}],
                    "containers": [{"name": "api", "image": f"x@{DIGEST}", "resources": FULL}],
                }
            }
        },
    }
    problems = check_k8s_documents([doc])
    assert any("container migrate" in p and "05 C-43" in p for p in problems)
    assert any("container migrate" in p and "05 C-44" in p for p in problems)


def test_non_workload_documents_are_ignored() -> None:
    docs = [{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "c"}}, None, "text"]
    assert check_k8s_documents(docs) == []


def test_dockerfile_from_without_digest_rejected() -> None:
    bad = "FROM python:3.12-slim\nRUN true\n"
    assert any("05 C-43" in p for p in check_dockerfile(bad))
    assert any("05 C-43" in p for p in check_dockerfile("FROM python:3.12-slim@sha256:123\n"))


def test_dockerfile_control_with_stages_passes() -> None:
    good = (
        f"FROM python:3.12-slim@{DIGEST} AS build\nRUN true\n"
        f"FROM --platform=linux/amd64 python:3.12-slim@{DIGEST}\nCOPY --from=build /x /x\n"
        "FROM build AS test\nFROM scratch\n"
    )
    assert check_dockerfile(good) == []


def test_unpinned_action_rejected() -> None:
    for ref in (
        "actions/checkout@v4",
        "actions/checkout@main",
        "actions/checkout",
        "docker://python:3.12",
    ):
        problems = check_workflow(f"steps:\n  - uses: {ref}\n")
        assert any("05 C-42" in p for p in problems), ref


def test_pinned_action_and_local_action_pass() -> None:
    sha = "11bd71901bbe5b1630ceea73d27597364c9af683"
    text = (
        f"steps:\n  - uses: actions/checkout@{sha} # v4.2.2\n"
        f"  - uses: github/codeql-action/init@{sha}\n  - uses: ./.github/actions/local\n"
        f"  - uses: docker://ghcr.io/x/y@{DIGEST}\n"
    )
    assert check_workflow(text) == []


def test_repository_passes_and_rendered_manifest_is_checked(tmp_path: Path) -> None:
    assert scan(REPO, []) == []
    rendered = tmp_path / "rendered.yaml"
    rendered.write_text(yaml.safe_dump_all([_cronjob("x:latest", None)]))
    problems = scan(REPO, [rendered])
    assert any("05 C-43" in p for p in problems) and any("05 C-44" in p for p in problems)


def test_unparsable_yaml_under_deployment_is_reported(tmp_path: Path) -> None:
    (tmp_path / "deployment").mkdir()
    (tmp_path / "deployment" / "broken.yaml").write_text("kind: [\n")
    assert any("unparsable" in p for p in scan(tmp_path, []))
