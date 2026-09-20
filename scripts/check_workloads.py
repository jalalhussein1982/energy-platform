"""Supply-chain and quota gates on whatever deploys (A-8, ADR-016; 05 C-42…C-44).

- every container of a Pod-bearing Kubernetes object has CPU and memory requests **and** limits;
- every image reference is pinned by digest (``name@sha256:<64 hex>``); ``:latest`` or a bare tag
  is refused;
- every Dockerfile ``FROM`` is pinned by digest (``scratch`` and build stages excepted);
- every GitHub Actions ``uses:`` is pinned to a 40-hex commit.

Scans ``.github/workflows/*.yml``, ``deployment/**/Dockerfile*`` and ``deployment/**/*.y*ml``;
extra rendered manifests (``helm template`` output) are passed as arguments.

Usage: check_workloads.py [rendered.yaml ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

DIGEST_IMAGE = re.compile(r"^[A-Za-z0-9./_:-]+@sha256:[0-9a-f]{64}$")
ACTION_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[A-Za-z0-9_./-]+)?@[0-9a-f]{40}$")
FROM_LINE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.IGNORECASE)

POD_SPEC_PATH: dict[str, tuple[str, ...]] = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "ReplicaSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}


def _dig(obj: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def check_image(image: str, where: str) -> list[str]:
    if DIGEST_IMAGE.match(image):
        return []
    if ":latest" in image or "@" not in image:
        return [f"{where}: image {image!r} is not pinned by digest (ADR-016 §1; 05 C-43)"]
    return [f"{where}: image {image!r} is not a valid digest reference (05 C-43)"]


def check_k8s_documents(docs: list[Any], source: str = "<yaml>") -> list[str]:
    problems: list[str] = []
    for index, doc in enumerate(docs):
        if not isinstance(doc, dict) or "kind" not in doc:
            continue
        kind = str(doc.get("kind"))
        name = _dig(doc, ("metadata", "name")) or f"#{index}"
        where = f"{source}: {kind}/{name}"
        if kind not in POD_SPEC_PATH:
            continue
        pod = _dig(doc, POD_SPEC_PATH[kind])
        if not isinstance(pod, dict):
            problems.append(f"{where}: no pod spec found")
            continue
        containers = list(pod.get("containers") or []) + list(pod.get("initContainers") or [])
        if not containers:
            problems.append(f"{where}: no containers")
        for c in containers:
            cname = c.get("name", "?") if isinstance(c, dict) else "?"
            cwhere = f"{where} container {cname}"
            if not isinstance(c, dict):
                problems.append(f"{cwhere}: not a mapping")
                continue
            problems.extend(check_image(str(c.get("image", "")), cwhere))
            resources = c.get("resources") or {}
            for section in ("requests", "limits"):
                block = resources.get(section) if isinstance(resources, dict) else None
                for resource in ("cpu", "memory"):
                    if not isinstance(block, dict) or resource not in block:
                        problems.append(
                            f"{cwhere}: resources.{section}.{resource} missing (A-8; 05 C-44)"
                        )
    return problems


def check_dockerfile(text: str, source: str = "Dockerfile") -> list[str]:
    problems: list[str] = []
    stages: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        m = FROM_LINE.match(line)
        if not m:
            continue
        image, stage = m.group(1), m.group(2)
        if stage:
            stages.add(stage)
        if image == "scratch" or image in stages:
            continue
        if not DIGEST_IMAGE.match(image):
            problems.append(
                f"{source}:{lineno}: FROM {image} is not pinned by digest (ADR-016 §1; 05 C-43)"
            )
    return problems


def check_workflow(text: str, source: str = "workflow.yml") -> list[str]:
    problems: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.split("#", 1)[0].strip()
        if not stripped.startswith(("- uses:", "uses:")):
            continue
        ref = stripped.split("uses:", 1)[1].strip().strip("'\"")
        if ref.startswith("./"):
            continue
        if ref.startswith("docker://"):
            if DIGEST_IMAGE.match(ref[len("docker://") :]):
                continue
            problems.append(f"{source}:{lineno}: {ref} is not pinned by digest (05 C-42)")
            continue
        if not ACTION_PIN.match(ref):
            problems.append(
                f"{source}:{lineno}: uses: {ref} is not pinned to a 40-hex commit (05 C-42)"
            )
    return problems


def _check_yaml_file(path: Path) -> list[str]:
    try:
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        return [f"{path}: unparsable YAML: {str(exc).splitlines()[0]}"]
    return check_k8s_documents(docs, str(path))


def scan(repo: Path, extra: list[Path]) -> list[str]:
    problems: list[str] = []
    for wf in sorted((repo / ".github" / "workflows").glob("*.y*ml")):
        problems.extend(check_workflow(wf.read_text(encoding="utf-8"), str(wf)))
    deployment = repo / "deployment"
    if deployment.is_dir():
        for df in sorted(p for p in deployment.rglob("Dockerfile*") if p.is_file()):
            problems.extend(check_dockerfile(df.read_text(encoding="utf-8"), str(df)))
        for yf in sorted(p for p in deployment.rglob("*.y*ml") if p.is_file()):
            if "templates" in yf.parts:  # Helm templates are checked rendered (helm-lint)
                continue
            problems.extend(_check_yaml_file(yf))
    for path in extra:
        problems.extend(_check_yaml_file(path))
    return problems


def main(argv: list[str]) -> int:
    problems = scan(Path("."), [Path(a) for a in argv[1:]])
    if problems:
        print("workload-check: violations (A-8, ADR-016):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("workload-check: OK (action pins, image digests, requests/limits)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
