"""The chart contract (ADR-001 amend, ADR-003 rev., ADR-025, ADR-026; 05 C-56, C-57), proven on
`helm template` output. Skips visibly without helm on PATH; CI installs it (`make helm-lint`
is the gate that runs the same renders through the two checker scripts)."""

from __future__ import annotations

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
    assert backup["initContainers"][0]["command"][0] == "pg_basebackup"
    assert "-X" in backup["initContainers"][0]["command"]
    assert backup["affinity"]["podAffinity"]  # pinned next to Postgres: the WAL claim is RWO
    drill = local["ep-energy-platform-restore-drill"]["spec"]["jobTemplate"]["spec"]["template"][
        "spec"
    ]
    names = [c["name"] for c in drill["initContainers"]]
    assert names == ["fetch", "prep", "scratch-postgres"]
    assert drill["initContainers"][2]["restartPolicy"] == "Always"  # native sidecar
    assert "B:bronze-replica/backups/postgres/base/" in drill["initContainers"][0]["args"][0]
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
