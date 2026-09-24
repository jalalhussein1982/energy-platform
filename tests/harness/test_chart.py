"""The chart contract (ADR-001 amend, ADR-003 rev., ADR-025, ADR-026; 05 C-56, C-57), proven on
`helm template` output. Skips visibly without helm on PATH; CI installs it (`make helm-lint`
is the gate that runs the same renders through the two checker scripts)."""

from __future__ import annotations

import ipaddress
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts.check_restricted_pss import check_documents
from scripts.check_workloads import check_k8s_documents
from scripts.render_target_values import target_values

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "deployment" / "helm" / "energy-platform"
DIGEST = "sha256:" + "0" * 64
CRD_BACKED = {
    "CustomResourceDefinition",
    "Cluster",
    "PodMonitor",
    "PrometheusRule",
    "ExternalSecret",
    "CiliumNetworkPolicy",
}

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not on PATH")


def _targets_file(tmp_path: Path) -> Path:
    targets, problems = target_values(REPO / "targets")
    assert problems == []
    path = tmp_path / "targets.yaml"
    path.write_text(yaml.safe_dump({"targets": targets}), encoding="utf-8")
    return path


def render(tmp_path: Path, *values: Path, extra: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    cmd = [
        "helm",
        "template",
        "ep",
        str(CHART),
        "--set",
        f"image.digest={DIGEST}",
        "-f",
        str(_targets_file(tmp_path)),
    ]
    for v in values:
        cmd += ["-f", str(v)]
    cmd += list(extra)
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout  # noqa: S603
    return [d for d in yaml.safe_load_all(out) if isinstance(d, dict)]


def kinds(docs: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(d["kind"]) for d in docs)


def named(docs: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    return {d["metadata"]["name"]: d for d in docs if d["kind"] == kind}


TENANT = REPO / "deployment" / "tenant" / "values-tenant.yaml"
DEMO = REPO / "deployment" / "tenant" / "values-demo.yaml"
LOCAL = REPO / "deployment" / "local" / "values-local.yaml"
ALL_FLAGS = CHART / "ci" / "all-flags-values.yaml"


def test_default_tenant_render_has_no_crd_backed_kind(tmp_path: Path) -> None:
    assert not (set(kinds(render(tmp_path, TENANT))) & CRD_BACKED)


def test_every_render_is_digest_pinned_resourced_and_restricted(tmp_path: Path) -> None:
    for values in (TENANT, LOCAL, ALL_FLAGS):
        docs = render(tmp_path, values)
        assert check_k8s_documents(docs, values.name) == []
        assert check_documents(docs, values.name) == []


def test_one_cronjob_template_rendered_per_target(tmp_path: Path) -> None:
    docs = render(tmp_path, TENANT)
    cronjobs = named(docs, "CronJob")
    for tid in ("ote-intraday-market", "ote-intraday-market-xlsx", "ceps-load", "ote-dam"):
        assert f"ep-energy-platform-capture-{tid}"[:52].rstrip("-") in cronjobs
        assert f"ep-energy-platform-process-{tid}"[:52].rstrip("-") in cronjobs
        assert f"ep-energy-platform-recapture-{tid}"[:52].rstrip("-") in cronjobs
        assert f"ep-energy-platform-backfill-{tid}"[:52].rstrip("-") in cronjobs
    assert "ep-energy-platform-gaps" in cronjobs
    process = cronjobs["ep-energy-platform-process-ote-intraday-market"]
    assert process["spec"]["schedule"] == "3-59/15 * * * *"  # never races the capture
    backfill = cronjobs["ep-energy-platform-backfill-ote-intraday-market"]
    bargs = backfill["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["args"]
    assert bargs == [
        "backfill",
        "-m",
        "/app/targets/ote_intraday_market/manifest.yaml",
        "--live",
        "--limit",
        "8",
    ]
    for cj in cronjobs.values():
        assert cj["spec"]["concurrencyPolicy"] == "Forbid"
        assert cj["spec"]["timeZone"] == "Europe/Prague"
        assert cj["spec"]["jobTemplate"]["spec"]["backoffLimit"] == 0
    capture = cronjobs["ep-energy-platform-capture-ote-intraday-market"]
    args = capture["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["args"]
    assert args[:3] == ["capture", "-m", "/app/targets/ote_intraday_market/manifest.yaml"]
    assert "--live" in args and "--start-jitter-seconds" in args
    assert capture["spec"]["schedule"] == "*/15 * * * *"
    recapture = cronjobs["ep-energy-platform-recapture-ote-intraday-market"]
    assert recapture["spec"]["schedule"] == "7 * * * *"
    rargs = recapture["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["args"]
    assert rargs[:5] == [
        "recapture",
        "-m",
        "/app/targets/ote_intraday_market/manifest.yaml",
        "--days",
        "3",
    ]


def test_hook_chain_matches_adr_025(tmp_path: Path) -> None:
    jobs = named(render(tmp_path, TENANT), "Job")
    migrate = jobs["ep-energy-platform-migrate"]["metadata"]["annotations"]
    smoke = jobs["ep-energy-platform-smoke"]["metadata"]["annotations"]
    assert (
        migrate["helm.sh/hook"] == "post-install,pre-upgrade"
        and migrate["helm.sh/hook-weight"] == "-10"
    )
    assert (
        smoke["helm.sh/hook"] == "post-install,post-upgrade,test"
        and smoke["helm.sh/hook-weight"] == "0"
    )
    assert "ep-energy-platform-storage-probe" not in jobs  # tiering.mode=none
    for job in (migrate, smoke):
        assert job["helm.sh/hook-delete-policy"] == "before-hook-creation,hook-succeeded"
    probe = named(render(tmp_path, ALL_FLAGS), "Job")["ep-energy-platform-storage-probe"]
    assert probe["metadata"]["annotations"]["helm.sh/hook-weight"] == "-5"
    assert probe["metadata"]["annotations"]["helm.sh/hook"] == "post-install,post-upgrade"


def test_smoke_uses_throwaway_bronze_and_the_fixture(tmp_path: Path) -> None:
    smoke = named(render(tmp_path, TENANT), "Job")["ep-energy-platform-smoke"]
    container = smoke["spec"]["template"]["spec"]["containers"][0]
    env = {e["name"]: e.get("value") for e in container["env"]}
    assert env["ENERGY_PLATFORM_BRONZE"] == "dir"
    assert env["ENERGY_PLATFORM_BRONZE_DIR"] == "/tmp/smoke-bronze"  # noqa: S108 — an emptyDir
    assert container["args"] == [
        "smoke",
        "-m",
        "/app/targets/ote_intraday_market/manifest.yaml",
        "--fixture",
        "/app/targets/ote_intraday_market/fixtures/ordinary_day",
    ]


def test_only_fetching_roles_get_internet_egress(tmp_path: Path) -> None:
    policies = named(render(tmp_path, TENANT), "NetworkPolicy")
    fetch = policies["ep-energy-platform-allow-internet-fetch"]
    roles = fetch["spec"]["podSelector"]["matchExpressions"][0]["values"]
    assert set(roles) == {"capture", "recapture", "backfill"}
    block = fetch["spec"]["egress"][0]["to"][0]["ipBlock"]
    assert block["cidr"] == "0.0.0.0/0"
    assert {"169.254.0.0/16", "10.0.0.0/8", "127.0.0.0/8", "100.64.0.0/10"} <= set(block["except"])
    assert fetch["spec"]["egress"][0]["ports"] == [{"protocol": "TCP", "port": 443}]
    deny = policies["ep-energy-platform-default-deny"]
    assert set(deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    assert "ep-energy-platform-allow-dns" in policies


def test_flags_render_their_crd_kinds_only_when_on(tmp_path: Path) -> None:
    on = kinds(render(tmp_path, ALL_FLAGS))
    assert on["Cluster"] == 1 and on["ExternalSecret"] == 1 and on["CiliumNetworkPolicy"] == 1
    assert on["StatefulSet"] == 0  # cnpg replaces the chart's own Postgres
    local = kinds(render(tmp_path, LOCAL))
    assert local["StatefulSet"] == 3  # postgres + minio a + minio b
    assert "Cluster" not in local


def test_every_workload_carries_residency_and_role(tmp_path: Path) -> None:
    for d in render(tmp_path, LOCAL):
        if d["kind"] in {"CronJob", "Job", "StatefulSet", "Deployment"}:
            labels = d["metadata"]["labels"]
            assert labels["energy-platform.io/residency"] == "local"
            assert labels.get("energy-platform.io/role"), d["metadata"]["name"]


def test_missing_digest_or_residency_is_refused(tmp_path: Path) -> None:
    for extra in (("--set", "image.digest=latest"), ("--set", "residency=")):
        cmd = [
            "helm",
            "template",
            "ep",
            str(CHART),
            "-f",
            str(TENANT),
            "-f",
            str(_targets_file(tmp_path)),
            *extra,
        ]
        if "residency=" in extra:
            cmd += ["--set", f"image.digest={DIGEST}"]
        result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        assert result.returncode != 0


def test_external_postgres_mode_refuses_an_empty_destination_list(tmp_path: Path) -> None:
    """C-68 (review 2 DEP-04): an empty `to:` list is every destination, so the render must fail."""
    base = [
        "helm",
        "template",
        "ep",
        str(CHART),
        "-f",
        str(TENANT),
        "-f",
        str(_targets_file(tmp_path)),
        "--set",
        f"image.digest={DIGEST}",
        "--set",
        "postgres.mode=external",
    ]
    refused = subprocess.run(base, capture_output=True, text=True)  # noqa: S603
    assert refused.returncode != 0 and "egress.postgres.cidrs is required" in refused.stderr
    allowed = subprocess.run(  # noqa: S603
        [*base, "--set", "egress.postgres.cidrs[0]=10.9.8.0/24"],
        check=True,
        capture_output=True,
        text=True,
    )
    docs = [d for d in yaml.safe_load_all(allowed.stdout) if isinstance(d, dict)]
    rules = [
        rule
        for doc in docs
        if doc.get("kind") == "NetworkPolicy"
        for rule in (doc.get("spec", {}).get("egress") or [])
        if any(p.get("port") == 5432 for p in rule.get("ports", []))
    ]
    cidrs = [t.get("ipBlock", {}).get("cidr") for rule in rules for t in (rule.get("to") or [])]
    assert rules and all(rule.get("to") for rule in rules)
    assert cidrs and set(cidrs) == {"10.9.8.0/24"}


def test_dr_workloads_render_behind_their_flags(tmp_path: Path) -> None:
    """ADR-036: replication, backup shipping, tiering and the restore drill (Task 5.10)."""
    local = named(render(tmp_path, LOCAL), "CronJob")
    assert "ep-energy-platform-replicate" in local and "ep-energy-platform-pg-backup" in local
    assert "ep-energy-platform-restore-drill" in local and "ep-energy-platform-tier" not in local
    replicate = local["ep-energy-platform-replicate"]["spec"]["jobTemplate"]["spec"]["template"][
        "spec"
    ]
    script = replicate["containers"][0]["args"][0]
    assert "rclone copy A:bronze B:bronze-replica --immutable --checksum" in script  # whole bucket
    assert "rclone sync" not in script and "rclone check" in script and "--one-way" in script
    backup = local["ep-energy-platform-pg-backup"]["spec"]["jobTemplate"]["spec"]["template"][
        "spec"
    ]
    base = backup["initContainers"][0]["args"][0]
    assert "pg_basebackup" in base and "-X stream" in base
    assert "backup_label" in base and "> /backup/base/START_WAL" in base
    assert "> /backup/base/SYSTEM_ID" in base
    assert base.index("pg_isready") < base.index("pg_basebackup")
    assert "A:bronze/backups/postgres/$SYSID/base/$STAMP/" in backup["containers"][0]["args"][0]
    assert "wal-archive" not in {v["name"] for v in backup["volumes"]}  # base only (amendment 1)
    drill = local["ep-energy-platform-restore-drill"]["spec"]["jobTemplate"]["spec"]["template"][
        "spec"
    ]
    names = [c["name"] for c in drill["initContainers"]]
    assert names == ["fetch", "prep", "scratch-postgres"]
    assert drill["initContainers"][2]["restartPolicy"] == "Always"  # native sidecar
    fetch = drill["initContainers"][0]["args"][0]
    # newest base across clusters, then that cluster's WAL (ADR-036 amendment 1 §6)
    assert "rclone lsf -R B:bronze-replica/backups/postgres/" in fetch
    assert '"B:bronze-replica/backups/postgres/$SYSID/base/$LATEST"' in fetch
    assert '"B:bronze-replica/backups/postgres/$SYSID/wal"' in fetch
    assert "/restore/base/START_WAL" in fetch and "--files-from /restore/wal.list" in fetch
    assert "gzip -dc /restore/wal/%f.gz" in drill["initContainers"][1]["args"][0]
    env = {e["name"] for e in drill["containers"][0]["env"]}
    assert {
        "ENERGY_PLATFORM_S3_REPLICA_ENDPOINT",
        "BRONZE_REPLICA_ACCESS_KEY_ID",
        "ENERGY_PLATFORM_DSN",
    } <= env
    assert "--scratch-schema rebuild" in drill["containers"][0]["args"][0]
    flags = named(render(tmp_path, ALL_FLAGS), "CronJob")
    assert "ep-energy-platform-tier" not in flags  # lifecycle mode: the probe hook, no move job
    tenant = named(render(tmp_path, TENANT), "CronJob")
    assert "ep-energy-platform-pg-backup" in tenant and "ep-energy-platform-replicate" in tenant


def test_wal_archive_is_compressed_shipped_and_pruned(tmp_path: Path) -> None:
    """ADR-036 amendment 1: gzip at archive time, `rclone move` to A, the old key refused."""
    docs = render(tmp_path, LOCAL)
    conf = named(docs, "ConfigMap")["ep-energy-platform-postgres-config"]["data"]
    archive = next(
        line for line in conf["postgresql.conf"].splitlines() if "archive_command" in line
    )
    assert "gzip -n -c %p" in archive and '.part" && mv' in archive and "cmp -s" in archive
    ship = named(docs, "CronJob")["ep-energy-platform-pg-wal-ship"]
    assert ship["spec"]["schedule"] == "*/5 * * * *"
    pod = ship["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    script = pod["containers"][0]["args"][0]
    move = "rclone move /wal-archive A:bronze/backups/postgres/$SYSID/wal/ --immutable --checksum"
    assert move in script
    assert "--exclude '*.part'" in script and "rclone copy" not in script
    assert pod["affinity"]["podAffinity"]  # pinned next to Postgres: the WAL claim is RWO
    # the archive is named by the cluster (§6): a re-initialised cluster restarts WAL names
    sysid = pod["initContainers"][0]
    assert sysid["name"] == "system-id" and "pg_control_system()" in sysid["args"][0]
    # connect only once Postgres answers: a new pod's policy rule may lag its first packet
    assert sysid["args"][0].index("pg_isready") < sysid["args"][0].index("psql")
    assert "SYSID=$(cat /work/SYSTEM_ID)" in script
    claim = next(v for v in pod["volumes"] if v["name"] == "wal-archive")
    assert not claim["persistentVolumeClaim"].get("readOnly")  # move deletes after upload
    old_key = tmp_path / "old-key.yaml"
    old_key.write_text(
        yaml.safe_dump({"postgres": {"backup": {"schedule": "*/15 * * * *"}}}), encoding="utf-8"
    )
    cmd = ["helm", "template", "ep", str(CHART), "--set", f"image.digest={DIGEST}"]
    cmd += ["-f", str(_targets_file(tmp_path)), "-f", str(LOCAL), "-f", str(old_key)]
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    assert result.returncode != 0 and "baseSchedule" in result.stderr


def _pod_spec(doc: dict[str, Any]) -> dict[str, Any] | None:
    if doc["kind"] == "CronJob":
        return dict(doc["spec"]["jobTemplate"]["spec"]["template"]["spec"])
    if doc["kind"] in {"Job", "StatefulSet", "Deployment"}:
        return dict(doc["spec"]["template"]["spec"])
    return None


def test_demo_values_render_without_placeholders(tmp_path: Path) -> None:
    """Plan P5-D21/P5-D22: the demo render is complete once the deploy supplies the OCI
    namespace; every egress CIDR is a network; every platform-image pod can pull privately."""
    endpoint = ("--set", "bronze.replica.endpoint=https://ns.compat.example.invalid")
    docs = render(tmp_path, TENANT, DEMO, extra=endpoint)
    assert "REPLACE" not in yaml.safe_dump_all(docs)
    assert check_k8s_documents(docs, DEMO.name) == []
    assert check_documents(docs, DEMO.name) == []
    blocks = [
        to["ipBlock"]["cidr"]
        for d in docs
        if d["kind"] == "NetworkPolicy"
        for rule in d["spec"].get("egress", [])
        for to in rule.get("to", [])
        if "ipBlock" in to
    ]
    assert {"88.198.120.0/25", "134.70.40.0/21", "134.70.48.0/22"} <= set(blocks)
    pg = named(docs, "StatefulSet")["ep-energy-platform-postgres"]["spec"]["template"]["spec"]
    # the Hetzner volume is mounted on the server only; local-path is node-local
    assert pg["nodeSelector"] == {"kubernetes.io/hostname": "energy-platform-demo-server"}
    assert (
        "nodeSelector"
        not in named(render(tmp_path, TENANT), "StatefulSet")["ep-energy-platform-postgres"][
            "spec"
        ]["template"]["spec"]
    )
    for cidr in blocks:
        ipaddress.ip_network(cidr)  # strict: raises on a placeholder or host bits
    platform = [s for s in map(_pod_spec, docs) if s is not None]
    platform = [s for s in platform if any(DIGEST in c["image"] for c in s.get("containers", []))]
    assert platform
    for spec in platform:
        assert spec.get("imagePullSecrets") == [{"name": "ghcr-pull"}]
    tenant = [s for s in map(_pod_spec, render(tmp_path, TENANT)) if s is not None]
    assert all("imagePullSecrets" not in s for s in tenant)  # nothing rendered by default
    cmd = ["helm", "template", "ep", str(CHART), "--set", f"image.digest={DIGEST}"]
    cmd += ["-f", str(_targets_file(tmp_path)), "-f", str(TENANT), "-f", str(DEMO)]
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    assert result.returncode != 0 and "endpoint is required" in result.stderr


def test_smoke_env_has_no_duplicate_keys_and_uses_dir_bronze(tmp_path: Path) -> None:
    smoke = named(render(tmp_path, TENANT), "Job")["ep-energy-platform-smoke"]
    env = [e["name"] for e in smoke["spec"]["template"]["spec"]["containers"][0]["env"]]
    assert len(env) == len(set(env)), env
    assert (
        dict(
            (e["name"], e.get("value"))
            for e in smoke["spec"]["template"]["spec"]["containers"][0]["env"]
        )["ENERGY_PLATFORM_BRONZE"]
        == "dir"
    )


def test_observability_renders_per_adr_037(tmp_path: Path) -> None:
    docs = render(tmp_path, TENANT)
    queries = named(docs, "ConfigMap")["ep-energy-platform-metrics-queries"]["data"]["queries.yaml"]
    parsed = yaml.safe_load(queries)
    exported = {
        f"{name}_{next(iter(col))}"
        for name, q in parsed.items()
        for col in q["metrics"]
        if next(iter(col.values()))["usage"] == "GAUGE"
    }
    assert {
        "energy_platform_freshness_age_seconds",
        "energy_platform_freshness_computed_age_seconds",
        "energy_platform_freshness_status_active",
        "energy_platform_freshness_periods_count",
        "energy_platform_source_unavailable",
        "energy_platform_pipeline_failed",
        "energy_platform_stale_fetch_streak",
        "energy_platform_runs_total",
        "energy_platform_quality_events_last_hour",
    } <= exported
    rules = yaml.safe_load(
        named(docs, "ConfigMap")["ep-energy-platform-alert-rules"]["data"][
            "energy-platform.rules.yaml"
        ]
    )
    names = {r["alert"] for g in rules["groups"] for r in g["rules"]}
    assert {
        "EnergyPlatformTargetLate",
        "EnergyPlatformPipelineFailed",
        "EnergyPlatformSourceUnavailable",
        "EnergyPlatformFreshnessStale",
        "EnergyPlatformRestoreDrillFailed",
        "EnergyPlatformReconciliationMismatch",
    } <= names
    exporter = named(docs, "Deployment")["ep-energy-platform-metrics"]
    annotations = exporter["spec"]["template"]["metadata"]["annotations"]
    assert (
        annotations["prometheus.io/scrape"] == "true"
        and annotations["prometheus.io/port"] == "9187"
    )
    env = {
        e["name"]: e.get("value")
        for e in exporter["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert env["DATA_SOURCE_NAME"].endswith("?sslmode=disable")  # statefulset mode
    assert "PodMonitor" not in kinds(docs) and "PrometheusRule" not in kinds(docs)
    flagged = kinds(render(tmp_path, ALL_FLAGS))
    assert flagged["PodMonitor"] == 1 and flagged["PrometheusRule"] == 1
    assert (CHART / "dashboards" / "freshness.json").is_file()


def _pod_specs(docs: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for d in docs:
        if d["kind"] == "CronJob":
            tpl = d["spec"]["jobTemplate"]["spec"]["template"]
        elif d["kind"] == "Job":
            tpl = d["spec"]["template"]
        else:
            continue
        out.append((tpl["metadata"]["labels"].get("energy-platform.io/role", ""), tpl["spec"]))
    return out


def test_policy_gate_runs_first_in_every_payload_pod_behind_its_flag(tmp_path: Path) -> None:
    """05 C-65: where the CNI applies a pod's policy asynchronously (the demo's kube-router),
    the work must not start before it is in force; off by default, on for demo and local."""
    payload_roles = {"capture", "process", "recapture", "backfill", "gaps", "hook"}
    for _, spec in _pod_specs(render(tmp_path, TENANT)):
        names = [c["name"] for c in spec.get("initContainers", [])]
        assert "egress-policy-gate" not in names  # default: no gate
    demo_endpoint = (
        "bronze.replica.endpoint=https://ns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com"
    )
    for values, extra in ((LOCAL, ()), (DEMO, ("--set", demo_endpoint))):
        specs = [(r, s) for r, s in _pod_specs(render(tmp_path, TENANT, values, extra=extra))]
        gated = [  # the platform image's pods (minio-init, a local hook, runs mc)
            (r, s) for r, s in specs if r in payload_roles and DIGEST in s["containers"][0]["image"]
        ]
        assert {r for r, _ in gated} >= {
            "capture",
            "process",
            "recapture",
            "backfill",
            "gaps",
            "hook",
        }
        for role, spec in gated:
            first = spec["initContainers"][0]
            assert first["name"] == "egress-policy-gate", (values.name, role)
            assert first["args"][:1] == ["wait-egress-policy"]
            assert all("valueFrom" not in e for e in first.get("env", []))  # no credential
            assert first["securityContext"]["readOnlyRootFilesystem"] is True
