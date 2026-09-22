"""Restricted Pod Security profile on rendered manifests (A-14; ADR-001 amend rule 3; 05 C-57).

For every Pod-bearing kind (Pod, Deployment, StatefulSet, DaemonSet, ReplicaSet, Job, CronJob):

- pod ``securityContext.runAsNonRoot: true`` (or on every container);
- pod ``securityContext.seccompProfile.type`` ∈ {RuntimeDefault, Localhost} (or on every container);
- every container and init container: ``allowPrivilegeEscalation: false``,
  ``capabilities.drop`` contains ``ALL`` and ``capabilities.add`` ⊆ {NET_BIND_SERVICE},
  not ``privileged``, no ``hostPort``;
- no ``hostNetwork`` / ``hostPID`` / ``hostIPC``; no ``hostPath`` volume; no ``hostProcess``.

Rendered chart output is passed as arguments (``helm template … > file``), like check_workloads.

Usage: check_restricted_pss.py rendered.yaml [...]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

POD_SPEC_PATH: dict[str, tuple[str, ...]] = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "ReplicaSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}
SECCOMP_OK = {"RuntimeDefault", "Localhost"}
CAP_ADD_OK = {"NET_BIND_SERVICE"}


def _dig(obj: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def check_pod_spec(pod: dict[str, Any], where: str) -> list[str]:
    problems: list[str] = []
    psc = pod.get("securityContext") or {}
    for flag in ("hostNetwork", "hostPID", "hostIPC"):
        if pod.get(flag):
            problems.append(f"{where}: {flag} is set")
    for volume in pod.get("volumes") or []:
        if isinstance(volume, dict) and "hostPath" in volume:
            problems.append(f"{where}: hostPath volume {volume.get('name')!r}")
    if _dig(psc, ("windowsOptions", "hostProcess")):
        problems.append(f"{where}: hostProcess pod")
    containers = list(pod.get("containers") or []) + list(pod.get("initContainers") or [])
    pod_nonroot = psc.get("runAsNonRoot") is True
    pod_seccomp = _dig(psc, ("seccompProfile", "type")) in SECCOMP_OK
    for c in containers:
        if not isinstance(c, dict):
            continue
        cname = c.get("name", "?")
        cwhere = f"{where} container {cname}"
        csc = c.get("securityContext") or {}
        if not pod_nonroot and csc.get("runAsNonRoot") is not True:
            problems.append(f"{cwhere}: runAsNonRoot is not true (pod or container)")
        if not pod_seccomp and _dig(csc, ("seccompProfile", "type")) not in SECCOMP_OK:
            problems.append(f"{cwhere}: seccompProfile.type is not RuntimeDefault/Localhost")
        if csc.get("allowPrivilegeEscalation") is not False:
            problems.append(f"{cwhere}: allowPrivilegeEscalation must be false")
        if csc.get("privileged"):
            problems.append(f"{cwhere}: privileged")
        caps = csc.get("capabilities") or {}
        drop = [str(x).upper() for x in (caps.get("drop") or [])]
        if "ALL" not in drop:
            problems.append(f"{cwhere}: capabilities.drop must contain ALL")
        add = {str(x).upper() for x in (caps.get("add") or [])}
        if add - CAP_ADD_OK:
            problems.append(f"{cwhere}: capabilities.add {sorted(add - CAP_ADD_OK)} not allowed")
        for port in c.get("ports") or []:
            if isinstance(port, dict) and port.get("hostPort"):
                problems.append(f"{cwhere}: hostPort")
    return problems


def check_documents(docs: list[Any], source: str = "<yaml>") -> list[str]:
    problems: list[str] = []
    for index, doc in enumerate(docs):
        if not isinstance(doc, dict) or "kind" not in doc:
            continue
        kind = str(doc.get("kind"))
        if kind not in POD_SPEC_PATH:
            continue
        name = _dig(doc, ("metadata", "name")) or f"#{index}"
        pod = _dig(doc, POD_SPEC_PATH[kind])
        where = f"{source}: {kind}/{name}"
        if not isinstance(pod, dict):
            problems.append(f"{where}: no pod spec found")
            continue
        problems.extend(check_pod_spec(pod, where))
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_restricted_pss.py rendered.yaml [...]", file=sys.stderr)
        return 2
    problems: list[str] = []
    for arg in argv[1:]:
        path = Path(arg)
        try:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            problems.append(f"{path}: unparsable YAML: {str(exc).splitlines()[0]}")
            continue
        problems.extend(check_documents(docs, str(path)))
    if problems:
        print("restricted-pss: violations (A-14, ADR-001 amend rule 3):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("restricted-pss: OK (every pod is restricted-profile clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
