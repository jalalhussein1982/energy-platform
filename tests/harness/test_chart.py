"""The chart contract (ADR-001 amend, ADR-003 rev., ADR-025, ADR-026; 05 C-56, C-57), proven on
`helm template` output. Skips visibly without helm on PATH; CI installs it (`make helm-lint`
is the gate that runs the same renders through the two checker scripts)."""

from __future__ import annotations

import ipaddress
import json
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
    assert recapture["spec"]["schedule"] == "7 3 * * *"
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
    assert local["StatefulSet"] == 3  # postgres + object store a + object store b (RustFS)
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
        "--set",
        "drills.restore.enabled=false",  # ADR-036 amendment 3: external has no drill chain
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
        "EnergyPlatformReplicationStale",
        "EnergyPlatformWalShipmentStale",
        "EnergyPlatformBaseBackupStale",
    } <= names
    stale = {r["alert"]: r["expr"] for g in rules["groups"] for r in g["rules"]}
    assert "kube_cronjob_status_last_successful_time" in stale["EnergyPlatformReplicationStale"]
    assert stale["EnergyPlatformReplicationStale"].endswith("> 7200")  # 2 x the hourly default
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
        gated = [  # the platform image's pods (every hook is the platform image since Phase 12)
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
            # ADR-026 amendment 3: the policy canary is the cluster DNS service's metrics port
            assert "--dns-metrics-canary-port" in first["args"]
            assert first["args"][first["args"].index("--dns-metrics-canary-port") + 1] == "9153"
            assert all("valueFrom" not in e for e in first.get("env", []))  # no credential
            assert first["securityContext"]["readOnlyRootFilesystem"] is True


def test_demo_replicates_every_fifteen_minutes_and_alerts_on_staleness(tmp_path: Path) -> None:
    """ADR-036 amendment 2 (review 2 DEP-01): the independent copy follows the capture cadence
    on the demo, and the alert thresholds follow the schedules."""
    docs = render(
        tmp_path, TENANT, DEMO, extra=("--set", "bronze.replica.endpoint=https://b.example")
    )
    replicate = named(docs, "CronJob")["ep-energy-platform-replicate"]
    assert replicate["spec"]["schedule"] == "7,22,37,52 * * * *"
    rules = yaml.safe_load(
        named(docs, "ConfigMap")["ep-energy-platform-alert-rules"]["data"][
            "energy-platform.rules.yaml"
        ]
    )
    exprs = {r["alert"]: r["expr"] for g in rules["groups"] for r in g["rules"]}
    assert exprs["EnergyPlatformReplicationStale"].endswith("> 2700")
    assert exprs["EnergyPlatformWalShipmentStale"].endswith("> 1800")
    assert exprs["EnergyPlatformBaseBackupStale"].endswith("> 172800")


def test_the_drill_refuses_database_modes_without_a_backup_chain(tmp_path: Path) -> None:
    """ADR-036 amendment 3 (review 2 DEP-02): cnpg / external render no backup objects the drill
    could restore, so enabling the drill with them is refused instead of silently accepted."""
    for mode in ("cnpg", "external"):
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
            f"postgres.mode={mode}",
            "--set",
            "egress.postgres.cidrs[0]=10.9.8.0/24",
        ]
        refused = subprocess.run(base, capture_output=True, text=True)  # noqa: S603
        assert (
            refused.returncode != 0
            and "drills.restore.enabled needs postgres.mode=statefulset" in refused.stderr
        )
        allowed = subprocess.run(  # noqa: S603
            [*base, "--set", "drills.restore.enabled=false"], capture_output=True, text=True
        )
        assert allowed.returncode == 0, allowed.stderr


def test_cilium_fqdn_mode_drops_the_broad_public_rule_and_carries_dns(tmp_path: Path) -> None:
    """ADR-026 amendment 3 (review 2 DEP-03): Cilium rules are a union, so the coarse public-443
    NetworkPolicy must not render beside the FQDN allowlist; the allowlist needs DNS visibility."""
    flagged = render(tmp_path, ALL_FLAGS)
    assert "ep-energy-platform-allow-internet-fetch" not in named(flagged, "NetworkPolicy")
    cilium = named(flagged, "CiliumNetworkPolicy")["ep-energy-platform-fqdn-fetch"]
    egress = cilium["spec"]["egress"]
    dns = next(rule for rule in egress if "toEndpoints" in rule)
    assert dns["toPorts"][0]["rules"]["dns"] == [{"matchPattern": "*"}]
    assert dns["toPorts"][0]["ports"][0]["port"] == "53"
    fqdn = next(rule for rule in egress if "toFQDNs" in rule)
    assert {f["matchName"] for f in fqdn["toFQDNs"]} >= {"www.ote-cr.cz", "www.ceps.cz"}
    assert "ep-energy-platform-allow-internet-fetch" in named(
        render(tmp_path, TENANT), "NetworkPolicy"
    )


def test_grafana_is_off_by_default_and_private_behind_its_flag(tmp_path: Path) -> None:
    """ADR-039: a window onto Silver, inside the cluster only — ClusterIP, read-only role, egress
    to Postgres and DNS, ingress from the namespace; nothing public; digest and PSS clean."""
    assert "ep-energy-platform-grafana" not in named(render(tmp_path, TENANT), "Deployment")
    docs = render(tmp_path, TENANT, LOCAL)
    grafana = named(docs, "Deployment")["ep-energy-platform-grafana"]
    spec = grafana["spec"]["template"]["spec"]
    assert spec["securityContext"]["runAsUser"] == 472
    container = spec["containers"][0]
    assert container["image"].startswith("docker.io/grafana/grafana@sha256:")
    env = {e["name"]: e for e in container["env"]}
    assert env["GF_AUTH_ANONYMOUS_ENABLED"]["value"] == "false"
    assert env["GF_ANALYTICS_REPORTING_ENABLED"]["value"] == "false"
    assert (
        env["GF_SECURITY_ADMIN_PASSWORD"]["valueFrom"]["secretKeyRef"]["key"]
        == "GRAFANA_ADMIN_PASSWORD"
    )
    assert env["GRAFANA_DB_PASSWORD"]["valueFrom"]["secretKeyRef"]["key"] == "GRAFANA_DB_PASSWORD"
    assert "ENERGY_PLATFORM_DSN" not in env and "POSTGRES_PASSWORD" not in env  # never the app's
    service = named(docs, "Service")["ep-energy-platform-grafana"]
    assert service["spec"]["type"] == "ClusterIP" and "Ingress" not in kinds(docs)
    provisioning = named(docs, "ConfigMap")["ep-energy-platform-grafana-provisioning"]["data"]
    datasource = yaml.safe_load(provisioning["datasource.yaml"])["datasources"][0]
    assert datasource["uid"] == "energy-postgres" and datasource["user"] == "grafana"
    assert datasource["jsonData"]["sslmode"] == "disable"  # statefulset mode, in-namespace
    secure = json.dumps(datasource["secureJsonData"])
    assert "$GRAFANA_DB_PASSWORD" in secure  # resolved from the Secret at start
    dashboards = named(docs, "ConfigMap")["ep-energy-platform-grafana-dashboards"]["data"]
    for name in ("prices.json", "freshness-sql.json"):
        board = json.loads(dashboards[name])
        assert board["editable"] is False and board["panels"]
        for panel in board["panels"]:
            assert panel["datasource"]["uid"] == "energy-postgres"
            for target in panel["targets"]:
                assert "rawSql" in target and target["rawQuery"] is True
    # the migrate hook grants the read-only role from the Secret, and nothing else changes
    migrate = named(docs, "Job")["ep-energy-platform-migrate"]["spec"]["template"]["spec"]
    hook = migrate["containers"][0]
    assert hook["args"] == ["migrate", "--reader-user", "grafana"]
    assert any(e["name"] == "GRAFANA_DB_PASSWORD" for e in hook["env"])
    tenant_hook = named(render(tmp_path, TENANT), "Job")["ep-energy-platform-migrate"]
    assert tenant_hook["spec"]["template"]["spec"]["containers"][0]["args"] == ["migrate"]
    # network: Postgres egress (the verb-role rule) and no internet; ingress from the namespace
    policies = named(docs, "NetworkPolicy")
    pg_roles = policies["ep-energy-platform-allow-postgres-egress"]["spec"]["podSelector"][
        "matchExpressions"
    ][0]["values"]
    fetch_roles = policies["ep-energy-platform-allow-internet-fetch"]["spec"]["podSelector"][
        "matchExpressions"
    ][0]["values"]
    assert "grafana" in pg_roles and "grafana" not in fetch_roles
    ingress = policies["ep-energy-platform-allow-grafana-ingress"]["spec"]["ingress"][0]
    assert ingress["from"] == [{"podSelector": {}}] and ingress["ports"] == [
        {"protocol": "TCP", "port": 3000}
    ]
    flagged = named(render(tmp_path, ALL_FLAGS), "ConfigMap")[
        "ep-energy-platform-grafana-provisioning"
    ]
    assert (
        yaml.safe_load(flagged["data"]["datasource.yaml"])["datasources"][0]["jsonData"]["sslmode"]
        == "require"
    )


def test_local_object_stores_are_rustfs_with_the_bucket_init_hook_on_the_platform_image(
    tmp_path: Path,
) -> None:
    """ADR-036 amendment 4: two RustFS StatefulSets (A locked, B plain) and a bucket-init hook
    that runs the platform's own client — no `mc`, no MinIO image anywhere in the render."""
    docs = render(tmp_path, TENANT, LOCAL)
    text = json.dumps(docs)
    assert "minio/minio" not in text and "minio/mc" not in text
    stores = {n: d for n, d in named(docs, "StatefulSet").items() if "minio-" in n}
    assert set(stores) == {"ep-energy-platform-minio-a", "ep-energy-platform-minio-b"}
    for name, sts in stores.items():
        spec = sts["spec"]["template"]["spec"]
        container = spec["containers"][0]
        assert container["image"].startswith("docker.io/rustfs/rustfs@sha256:")
        env = {e["name"]: e for e in container["env"]}
        secret = "BRONZE" if name.endswith("-a") else "BRONZE_REPLICA"
        assert (
            env["RUSTFS_ACCESS_KEY"]["valueFrom"]["secretKeyRef"]["key"]
            == f"{secret}_ACCESS_KEY_ID"
        )
        assert env["RUSTFS_CONSOLE_ENABLE"]["value"] == "false"
        assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
        assert spec["securityContext"]["runAsUser"] == 10001
    hook = named(docs, "Job")["ep-energy-platform-bucket-init"]
    pod = hook["spec"]["template"]["spec"]
    assert DIGEST in pod["containers"][0]["image"]
    assert pod["containers"][0]["args"] == ["bucket-init", "--replica"]
    hook_env = {e["name"] for e in pod["containers"][0]["env"]}
    assert {"ENERGY_PLATFORM_S3_ENDPOINT", "ENERGY_PLATFORM_S3_REPLICA_ENDPOINT"} <= hook_env
    assert hook["metadata"]["annotations"]["helm.sh/hook-weight"] == "-20"
    assert "ep-energy-platform-minio-init" not in named(docs, "Job")


def test_r2_the_capture_container_learns_its_job_name_by_the_downward_api(tmp_path: Path) -> None:
    """ADR-031 amendment 1 (review 3 R2): the run's instant is the CronJob controller's tick,
    carried in the Job name; only the capture verb needs it."""
    docs = render(tmp_path, TENANT)
    by_verb: dict[str, list[dict[str, Any]]] = {}
    for d in docs:
        if d["kind"] != "CronJob" or not d["metadata"]["name"].startswith("ep-energy-platform-"):
            continue
        container = d["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
        by_verb.setdefault(container["name"], []).append(container)
    for c in by_verb["capture"]:
        env = {e["name"]: e for e in c["env"]}
        ref = env["ENERGY_PLATFORM_JOB_NAME"]["valueFrom"]["fieldRef"]["fieldPath"]
        assert ref == "metadata.labels['batch.kubernetes.io/job-name']"
    for verb in ("process", "backfill", "recapture"):
        for c in by_verb.get(verb, []):
            assert "ENERGY_PLATFORM_JOB_NAME" not in {e["name"] for e in c["env"]}


def test_alerting_renders_behind_its_flag_without_cluster_rights(tmp_path: Path) -> None:
    """ADR-040 (review 3 R3): the evaluator, its metric source and the receiver render only
    behind `alerting.enabled`; no CRD, no ClusterRole; Prometheus loads the existing rules
    ConfigMap unchanged; Alertmanager routes to the platform receiver; kube-state-metrics is
    namespaced with a Role and reaches the API server only by the declared address."""
    tenant = render(tmp_path, TENANT)
    roles = {"prometheus", "alertmanager", "kube-state-metrics", "alert-sink"}
    assert not {d["metadata"]["name"] for d in tenant if d["kind"] == "Deployment"} & {
        f"ep-energy-platform-{r}" for r in roles
    }
    assert "Role" not in kinds(tenant) and "RoleBinding" not in kinds(tenant)
    demo_endpoint = (
        "bronze.replica.endpoint=https://ns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com"
    )
    for values, extra in ((LOCAL, ()), (DEMO, ("--set", demo_endpoint)), (ALL_FLAGS, ())):
        docs = render(tmp_path, TENANT, values, extra=extra)
        deployments = named(docs, "Deployment")
        for r in roles:
            assert f"ep-energy-platform-{r}" in deployments, (values.name, r)
        assert "ClusterRole" not in kinds(docs) and "ClusterRoleBinding" not in kinds(docs)
        role = named(docs, "Role")["ep-energy-platform-kube-state-metrics"]
        assert role["rules"] == [
            {"apiGroups": ["batch"], "resources": ["jobs", "cronjobs"], "verbs": ["list", "watch"]}
        ]
        ksm = deployments["ep-energy-platform-kube-state-metrics"]["spec"]["template"]["spec"]
        assert ksm["serviceAccountName"] == "ep-energy-platform-kube-state-metrics"
        assert "--namespaces=" in " ".join(ksm["containers"][0]["args"])
        assert "--resources=cronjobs,jobs" in ksm["containers"][0]["args"]
        # Prometheus mounts the SAME rules ConfigMap the tenant render already ships
        prom = deployments["ep-energy-platform-prometheus"]["spec"]["template"]["spec"]
        mounted = {v["configMap"]["name"] for v in prom["volumes"] if "configMap" in v}
        assert "ep-energy-platform-alert-rules" in mounted
        prom_cfg = yaml.safe_load(
            named(docs, "ConfigMap")["ep-energy-platform-prometheus"]["data"]["prometheus.yml"]
        )
        assert prom_cfg["rule_files"] == ["/etc/prometheus/rules/*.yaml"]
        targets = {
            t
            for sc in prom_cfg["scrape_configs"]
            for s in sc["static_configs"]
            for t in s["targets"]
        }
        assert targets == {
            "ep-energy-platform-metrics:9187",
            "ep-energy-platform-kube-state-metrics:8080",
        }
        assert prom_cfg["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"] == [
            "ep-energy-platform-alertmanager:9093"
        ]
        # Alertmanager: the platform receiver first, the operator's receivers appended
        am_cfg = yaml.safe_load(
            named(docs, "ConfigMap")["ep-energy-platform-alertmanager"]["data"]["alertmanager.yml"]
        )
        assert am_cfg["route"]["receiver"] == "platform-sink"
        sink = next(r for r in am_cfg["receivers"] if r["name"] == "platform-sink")
        assert (
            sink["webhook_configs"][0]["url"] == "http://ep-energy-platform-alert-sink:8080/alerts"
        )
        assert sink["webhook_configs"][0]["send_resolved"] is True
        # the receiver: the platform image, the verb, no platform environment (no DSN, no keys)
        sink_pod = deployments["ep-energy-platform-alert-sink"]["spec"]["template"]["spec"]
        assert sink_pod["containers"][0]["args"] == ["alert-sink", "--port", "8080"]
        assert {e["name"] for e in sink_pod["containers"][0]["env"]} == {"TMPDIR"}
        # default-deny stays: kube-state-metrics reaches the API server by the declared CIDRs only
        policies = named(docs, "NetworkPolicy")
        egress = policies["ep-energy-platform-allow-kube-state-metrics-egress"]["spec"]["egress"]
        assert [b["ipBlock"]["cidr"] for b in egress[0]["to"]] and egress[0]["ports"][0][
            "port"
        ] == 6443
        am_egress = policies["ep-energy-platform-allow-alertmanager-egress"]["spec"]["egress"]
        assert (
            am_egress[0]["to"][0]["podSelector"]["matchLabels"]["energy-platform.io/role"]
            == "alert-sink"
        )
        if values is ALL_FLAGS:
            assert am_egress[1]["to"][0]["ipBlock"]["cidr"] == "203.0.113.0/24"
            assert {r["name"] for r in am_cfg["receivers"]} == {"platform-sink", "ops-webhook"}
            assert am_cfg["route"]["routes"][0]["receiver"] == "ops-webhook"
        else:
            assert len(am_egress) == 1  # no internet for Alertmanager unless declared
        # Grafana gets the Prometheus datasource and the ADR-037 dashboard
        ds = yaml.safe_load(
            named(docs, "ConfigMap")["ep-energy-platform-grafana-provisioning"]["data"][
                "datasource.yaml"
            ]
        )
        assert {d["uid"] for d in ds["datasources"]} == {"energy-postgres", "energy-prometheus"}
        assert (
            "freshness.json"
            in named(docs, "ConfigMap")["ep-energy-platform-grafana-dashboards"]["data"]
        )
        assert "ep-energy-platform-allow-grafana-prometheus-egress" in policies
    # the address of the control plane is not optional
    with pytest.raises(subprocess.CalledProcessError) as refused:
        render(tmp_path, TENANT, extra=("--set", "alerting.enabled=true"))
    assert "alerting.kubeStateMetrics.apiServer.cidrs is required" in refused.value.stderr
