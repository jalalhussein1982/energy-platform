"""Golden runner: prove a target's expected rows against its Bronze fixture, offline (ADR-020).

The pipeline is the production one (``runtime.process.map_payload``: decode → generic parser →
mapping → completeness), fed with the fixture instead of a capture. A golden either lists rows
that must come out, identified as Silver identifies them (04 §2.3), or names the quarantine the
document must raise (01 §9). ``tests/harness/test_goldens.py`` runs every golden of every target;
``energyctl run-target-tests`` and the MCP ``run_target_tests`` tool run one target's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from energy_platform.bronze import BronzeError, load_fixture
from energy_platform.contracts.golden import GoldenError, GoldenFile, GoldenRow, load_golden
from energy_platform.contracts.manifest import Manifest, ManifestSyntaxError, load_manifest
from energy_platform.contracts.observation import EnergyObservation
from energy_platform.harness.surface import golden_paths, target_dirs
from energy_platform.mapping import MappingContext, QualityEvent, Quarantined
from energy_platform.parse import parser_ref
from energy_platform.runtime.context import delivery_day_for
from energy_platform.runtime.process import completeness_events, map_payload
from energy_platform.store import derivation_for


@dataclass(frozen=True, slots=True)
class GoldenReport:
    target_id: str
    golden: str
    fixture: str
    problems: tuple[str, ...]
    observations: int = 0
    events: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True, slots=True)
class PipelineOutcome:
    observations: tuple[EnergyObservation, ...]
    events: tuple[QualityEvent, ...]
    quarantine: str | None


def run_pipeline(
    manifest: Manifest, fixture_dir: Path, *, now: datetime | None = None
) -> PipelineOutcome:
    """The production path over one fixture; a quarantine is an outcome, not an exception."""
    entry, payload = load_fixture(fixture_dir)
    derivation = derivation_for(manifest, parser_ref(manifest))
    ctx = MappingContext(
        target_id=manifest.target_id,
        scheduled_for=entry.scheduled_for,
        delivery_day=delivery_day_for(entry.scheduled_for, manifest.mapping.time.timezone),
        fetched_at=entry.fetched_at,
        raw_ref=entry.raw_ref,
        payload_sha256=entry.payload_sha256,
        processed_at=now or datetime.now(UTC),
        derivation_id=derivation.derivation_id,
    )
    try:
        result = map_payload(manifest, payload, ctx)
    except Quarantined as q:
        return PipelineOutcome((), (q.as_event(),), q.reason)
    events = list(result.events)
    events.extend(completeness_events(result.observations, manifest.mapping.time.timezone))
    return PipelineOutcome(result.observations, tuple(events), None)


def _matches(row: GoldenRow, obs: EnergyObservation, manifest_dims: dict[str, str]) -> bool:
    if obs.metric != row.metric or obs.resolution != row.resolution:
        return False
    if obs.delivery_start_utc != row.delivery_start_utc.astimezone(UTC):
        return False
    expected_dims = row.dimensions if row.dimensions is not None else manifest_dims
    if dict(obs.dimensions) != dict(expected_dims):
        return False
    if "source_version" in row.model_fields_set and obs.source_version != row.source_version:
        return False
    return True


def _describe(row: GoldenRow) -> str:
    return f"{row.metric}@{row.delivery_start_utc.astimezone(UTC):%Y-%m-%dT%H:%MZ}/{row.resolution}"


def compare(golden: GoldenFile, outcome: PipelineOutcome, manifest: Manifest) -> list[str]:
    """Every way a golden can disagree with what the platform produced (05 C-17)."""
    problems: list[str] = []
    expect = golden.expect
    if expect.quarantine is not None:
        if outcome.quarantine is None:
            problems.append(
                f"expected a quarantine containing {expect.quarantine!r}, got "
                f"{len(outcome.observations)} rows"
            )
        elif expect.quarantine not in outcome.quarantine:
            problems.append(
                f"expected a quarantine containing {expect.quarantine!r}, "
                f"got {outcome.quarantine!r}"
            )
        return problems
    if outcome.quarantine is not None:
        problems.append(f"document was quarantined: {outcome.quarantine}")
        return problems
    if expect.row_count is not None and len(outcome.observations) != expect.row_count:
        problems.append(f"row_count: expected {expect.row_count}, got {len(outcome.observations)}")
    dims = dict(manifest.mapping.dimensions)
    for row in expect.rows:
        found = [o for o in outcome.observations if _matches(row, o, dims)]
        if not found:
            problems.append(f"{_describe(row)}: no such row was produced")
            continue
        obs = found[0]
        if obs.value != row.value:
            problems.append(f"{_describe(row)}: expected {row.value}, got {obs.value}")
        if row.period_index is not None and obs.period_index != row.period_index:
            problems.append(
                f"{_describe(row)}: expected period_index {row.period_index}, "
                f"got {obs.period_index}"
            )
    if expect.quality_events is not None:
        kinds = sorted({e.kind for e in outcome.events})
        if kinds != sorted(set(expect.quality_events)):
            problems.append(
                f"quality_events: expected {sorted(set(expect.quality_events))}, got {kinds}"
            )
    return problems


def run_golden(target: Path, golden_path: Path, *, now: datetime | None = None) -> GoldenReport:
    name = golden_path.name
    try:
        golden = load_golden(golden_path)
    except (GoldenError, ValidationError, OSError) as exc:
        return GoldenReport(target.name, name, "?", (f"golden unreadable: {exc}",))
    try:
        manifest = load_manifest(target / "manifest.yaml")
    except (ManifestSyntaxError, ValidationError, OSError) as exc:
        return GoldenReport(target.name, name, golden.fixture, (f"manifest unreadable: {exc}",))
    fixture_dir = target / "fixtures" / golden.fixture
    try:
        outcome = run_pipeline(manifest, fixture_dir, now=now)
    except (BronzeError, ValidationError, OSError, ValueError) as exc:
        return GoldenReport(target.name, name, golden.fixture, (f"fixture unusable: {exc}",))
    problems = compare(golden, outcome, manifest)
    return GoldenReport(
        target.name,
        name,
        golden.fixture,
        tuple(problems),
        len(outcome.observations),
        tuple(e.kind for e in outcome.events),
    )


def run_target(target: Path, *, now: datetime | None = None) -> tuple[GoldenReport, ...]:
    return tuple(run_golden(target, g, now=now) for g in golden_paths(target))


def discover(root: Path) -> tuple[tuple[Path, Path], ...]:
    """Every ``(target_dir, golden_path)`` under ``root`` — the test suite's parameter list."""
    return tuple((t, g) for t in target_dirs(root) for g in golden_paths(t))
