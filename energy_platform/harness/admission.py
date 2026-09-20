"""Route B, the honest way out (ADR-022 §2): an admission request, not an invented unit.

``energyctl admission-request <id>`` renders ``docs/admissions/<id>.md`` from
``docs/admissions/TEMPLATE.md`` with exactly the gaps ``validate_manifest`` reported. The PR that
carries it touches nothing else; CODEOWNERS reviews the registry change it asks for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from energy_platform.contracts.manifest import Manifest, ValidationResult, validate_manifest

TEMPLATE = Path("docs/admissions/TEMPLATE.md")


def render_request(
    manifest: Manifest, result: ValidationResult | None = None, *, template: Path = TEMPLATE
) -> str:
    result = result or validate_manifest(manifest)
    gaps = result.missing
    metrics = ", ".join(f"`{ds}.{m}`" for ds, m in gaps.metrics) or "none"
    hosts = ", ".join(f"`{h}`" for h in gaps.hosts) or "none"
    insecure = ", ".join(f"`{h}`" for h in gaps.insecure_hosts) or "none"
    datasets = ", ".join(f"`{d}`" for d in gaps.datasets) or "none"
    declared = "\n".join(
        f"| `{name}` | `{m.unit}` | {m.sign} | {m.decimal_separator} |"
        for name, m in manifest.mapping.metrics.items()
    )
    text = template.read_text(encoding="utf-8")
    return (
        text.replace("{{target_id}}", manifest.target_id)
        .replace("{{date}}", datetime.now(UTC).strftime("%Y-%m-%d"))
        .replace("{{status}}", result.status)
        .replace("{{dataset_id}}", manifest.contract.dataset_id)
        .replace("{{missing_datasets}}", datasets)
        .replace("{{missing_metrics}}", metrics)
        .replace("{{missing_hosts}}", hosts)
        .replace("{{missing_insecure_hosts}}", insecure)
        .replace("{{errors}}", "\n".join(f"- {e}" for e in result.errors) or "- none")
        .replace("{{license}}", manifest.license)
        .replace("{{terms_url}}", manifest.terms_url)
        .replace("{{allowed_hosts}}", ", ".join(f"`{h}`" for h in manifest.allowed_hosts))
        .replace("{{modality}}", manifest.modality)
        .replace("{{declared_metrics}}", declared)
    )


def write_request(manifest: Manifest, out_dir: Path, *, template: Path = TEMPLATE) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{manifest.target_id}.md"
    path.write_text(render_request(manifest, template=template), encoding="utf-8")
    return path
