"""``energyctl``: a thin client of the library (ADR-000).

Phase 2 verbs take ``--manifest``; Phase 3 verbs take a target id resolved against ``targets/``
(``--targets-root``). Persistence is PostgreSQL through ``--dsn`` / ``ENERGY_PLATFORM_DSN``;
Bronze is a directory through ``--bronze-dir`` / ``ENERGY_PLATFORM_BRONZE_DIR``. ``capture``
works without a database (ADR-024 §1). Live fetching is opt-in (``--live``); ``--fixture``
replays a Bronze fixture through the real fetch path with an offline transport (ADR-010).
The harness verbs (``new-target``, ``validate <id>``, ``record-fixture``, ``run-target-tests``,
``admission-request``, ``pr-bundle``, ``mcp-serve``) are wrappers over ``energy_platform.harness``
and ``energy_platform.mcp`` — the same code CI and the MCP server run (ADR-007).
"""

from __future__ import annotations

import json
import logging
import os
import random
import secrets
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from pydantic import ValidationError

from energy_platform.bronze import Bronze, FileBlobStore, FileCaptureLog, load_fixture
from energy_platform.bronze.config import (
    BronzeConfigError,
    bronze_from_env,
    object_store_from_env,
    replica_bronze_from_env,
)
from energy_platform.contracts.manifest import (
    Manifest,
    ManifestSyntaxError,
    Modality,
    load_manifest,
    validate_manifest,
)
from energy_platform.fetch import EnvSecretResolver, Fetcher, ObjectStoreError
from energy_platform.harness.admission import write_request
from energy_platform.harness.fixtures import FixtureError, record_from_file, record_live
from energy_platform.harness.pr import BundleRefused, prepare_bundle
from energy_platform.harness.runner import run_target_tests
from energy_platform.harness.scaffold import ScaffoldError, scaffold_target
from energy_platform.harness.surface import check_target, target_dirs
from energy_platform.mcp import serve_stdio
from energy_platform.runtime import (
    Runtime,
    backfill,
    capture,
    detect_gaps,
    fixture_fetcher_factory,
    process,
    recapture,
    record_freshness,
    replay_derivation,
    replay_range,
    restore_drill,
    smoke,
    storage_probe,
)
from energy_platform.silver import downgrade, upgrade
from energy_platform.silver.migrate import create_schema, drop_schema
from energy_platform.store import MemoryStore, Store, StoreUnavailable
from energy_platform.store.postgres import PostgresStore
from energy_platform.store.unavailable import UnavailableStore

app = typer.Typer(
    name="energyctl",
    help=(
        "energy-platform command line: validate, capture, recapture, process, replay, gaps, "
        "freshness, smoke, storage-probe, restore-drill, demo; new-target, record-fixture, "
        "run-target-tests, admission-request, pr-bundle, mcp-serve"
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

ManifestOpt = Annotated[Path, typer.Option("--manifest", "-m", help="path to a manifest.yaml")]
TargetsRootOpt = Annotated[
    Path,
    typer.Option("--targets-root", envvar="ENERGY_PLATFORM_TARGETS", help="the targets/ directory"),
]
TargetArg = Annotated[str, typer.Argument(help="target id (directory under targets/)")]
DsnOpt = Annotated[
    str | None,
    typer.Option("--dsn", envvar="ENERGY_PLATFORM_DSN", help="PostgreSQL DSN (>= 16, ADR-030)"),
]
BronzeOpt = Annotated[
    Path | None,
    typer.Option(
        "--bronze-dir",
        envvar="ENERGY_PLATFORM_BRONZE_DIR",
        help="Bronze directory (blobs + capture log); ENERGY_PLATFORM_BRONZE=s3 selects S3",
    ),
]
JitterOpt = Annotated[
    float,
    typer.Option(
        "--start-jitter-seconds",
        min=0.0,
        help="sleep a uniform random 0..N s before fetching (D-5 start jitter; a chart value)",
    ),
]

EXAMPLES = Path("examples")
TARGETS = Path("targets")
DEMO_TARGETS = ("ote_idm_soap", "ote_idm_xlsx", "ceps_load_soap")


def _echo(obj: Any) -> None:
    typer.echo(json.dumps(_plain(obj), default=str, ensure_ascii=False))


def _plain(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _plain(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, tuple | list):
        return [_plain(x) for x in obj]
    return obj


def _manifest(path: Path) -> Manifest:
    try:
        return load_manifest(path)
    except (ManifestSyntaxError, ValidationError, OSError) as exc:
        typer.echo(f"manifest: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _target_dir(root: Path, target_id: str) -> Path:
    target = root / target_id
    if not (target / "manifest.yaml").is_file():
        typer.echo(f"{target}/manifest.yaml not found (energyctl new-target {target_id})", err=True)
        raise typer.Exit(code=1)
    return target


def _target_manifest(root: Path, target_id: str) -> tuple[Path, Manifest]:
    target = _target_dir(root, target_id)
    m = _manifest(target / "manifest.yaml")
    if m.target_id != target_id:
        typer.echo(
            f"manifest target_id {m.target_id!r} must equal the directory name {target_id!r}",
            err=True,
        )
        raise typer.Exit(code=1)
    return target, m


def _store(dsn: str | None, *, required: bool) -> Store:
    if dsn is None:
        if required:
            typer.echo("a database is required: set ENERGY_PLATFORM_DSN or pass --dsn", err=True)
            raise typer.Exit(code=1)
        return UnavailableStore()
    try:
        return PostgresStore(dsn)
    except StoreUnavailable as exc:
        typer.echo(f"store: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _bronze(bronze_dir: Path | None) -> Bronze:
    """``--bronze-dir`` wins; otherwise the environment decides (P5-D4: ``dir`` or ``s3``)."""
    if bronze_dir is not None:
        return Bronze(FileBlobStore(bronze_dir), FileCaptureLog(bronze_dir))
    try:
        return bronze_from_env(os.environ)
    except (BronzeConfigError, ObjectStoreError) as exc:
        typer.echo(f"bronze: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _live_fetcher(manifest: Manifest) -> Fetcher:
    return Fetcher(allowed_hosts=manifest.allowed_hosts, allow_insecure=manifest.allow_insecure)


_fixture_factory = fixture_fetcher_factory


def _jitter(seconds: float) -> None:
    if seconds > 0:
        time.sleep(random.SystemRandom().uniform(0.0, seconds))


def _runtime(manifest: Manifest, store: Store, bronze: Bronze, fetcher_factory: Any) -> Runtime:
    return Runtime(
        manifest=manifest,
        bronze=bronze,
        store=store,
        fetcher_factory=fetcher_factory,
        secrets=EnvSecretResolver(),
    )


def _instant(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        typer.echo(f"{text!r}: timestamps must carry an offset (ADR-014)", err=True)
        raise typer.Exit(code=1)
    return value


# ---------------------------------------------------------------------------- commands


_EXIT = {"OK": 0, "INVALID": 1, "ADMISSION_REQUIRED": 2}


@app.command()
def validate(
    target_id: Annotated[str | None, typer.Argument(help="target id under targets/")] = None,
    manifest: Annotated[
        Path | None, typer.Option("--manifest", "-m", help="path to a manifest.yaml")
    ] = None,
    all_targets: Annotated[bool, typer.Option("--all", help="every target under targets/")] = False,
    targets_root: TargetsRootOpt = TARGETS,
) -> None:
    """Structural + admission validation; exit 0 OK, 1 INVALID, 2 ADMISSION_REQUIRED.

    With a target id the surface rules (ADR-027, 05 A-rows) run too; `--all` is the CI gate.
    """
    if all_targets:
        worst = 0
        for target in target_dirs(targets_root):
            worst = max(worst, _validate_target(targets_root, target.name))
        if not target_dirs(targets_root):
            typer.echo("validate: no targets yet — nothing to check")
        raise typer.Exit(code=worst)
    if (target_id is None) == (manifest is None):
        typer.echo("give a target id or --manifest PATH (or --all)", err=True)
        raise typer.Exit(code=1)
    if manifest is not None:
        result = validate_manifest(_manifest(manifest))
        _echo(result)
        raise typer.Exit(code=_EXIT[result.status])
    assert target_id is not None
    raise typer.Exit(code=_validate_target(targets_root, target_id))


def _validate_target(root: Path, target_id: str) -> int:
    target, m = _target_manifest(root, target_id)
    result = validate_manifest(m)
    surface = check_target(target)
    _echo({"target_id": target_id, "validation": _plain(result), "surface": surface})
    return max(_EXIT[result.status], 1 if surface else 0)


@app.command()
def migrate(
    dsn: DsnOpt = None,
    down: Annotated[str | None, typer.Option("--downgrade", help="target revision or base")] = None,
) -> None:
    """Apply the Silver/ledger migrations, or downgrade to a revision (each has one)."""
    if dsn is None:
        typer.echo("set ENERGY_PLATFORM_DSN or pass --dsn", err=True)
        raise typer.Exit(code=1)
    if down is not None:
        downgrade(dsn, down)
        typer.echo(f"downgraded to {down}")
    else:
        upgrade(dsn)
        typer.echo("migrated to head")


@app.command("capture")
def capture_cmd(
    manifest: ManifestOpt,
    scheduled_for: Annotated[
        str | None, typer.Option("--scheduled-for", help="ISO 8601 instant with offset")
    ] = None,
    fixture: Annotated[
        Path | None, typer.Option("--fixture", help="Bronze fixture dir (entry.json + blob)")
    ] = None,
    live: Annotated[bool, typer.Option("--live", help="fetch from the source (opt-in)")] = False,
    force: Annotated[bool, typer.Option("--force", help="capture again (new attempt)")] = False,
    start_jitter: JitterOpt = 0.0,
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
) -> None:
    """Fetch → write raw → acknowledge. Works without a database (ADR-024 §1)."""
    m = _manifest(manifest)
    if (fixture is None) == (not live):
        typer.echo("choose exactly one of --fixture DIR or --live", err=True)
        raise typer.Exit(code=1)
    if fixture is not None:
        entry, payload = load_fixture(fixture)
        when = _instant(scheduled_for) if scheduled_for else entry.scheduled_for
        factory: Any = _fixture_factory(payload, entry.content_type)
    else:
        when = _instant(scheduled_for) if scheduled_for else datetime.now(UTC)
        factory = _live_fetcher
    rt = _runtime(m, _store(dsn, required=False), _bronze(bronze_dir), factory)
    _jitter(start_jitter)
    report = capture(rt, when, force=force)
    _echo(report)
    raise typer.Exit(code=0 if report.outcome in {"ok", "noop"} else 1)


@app.command("recapture")
def recapture_cmd(
    manifest: ManifestOpt,
    days: Annotated[
        int, typer.Option("--days", min=1, help="re-capture the last run of D-1 … D-N (ADR-033)")
    ],
    live: Annotated[bool, typer.Option("--live", help="fetch from the source (opt-in)")] = False,
    start_jitter: JitterOpt = 0.0,
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
) -> None:
    """Correction re-poll (ADR-033 §3): a forced new attempt on each past day's last run; only a
    changed payload makes the run pending again. Live by definition, so --live is required."""
    if not live:
        typer.echo("recapture fetches from the source: pass --live (05 C-50)", err=True)
        raise typer.Exit(code=1)
    rt = _runtime(
        _manifest(manifest), _store(dsn, required=False), _bronze(bronze_dir), _live_fetcher
    )
    _jitter(start_jitter)
    failed = False
    for report in recapture(rt, days=days):
        _echo(report)
        if report.capture is not None and report.capture.outcome not in {"ok", "noop"}:
            failed = True
    raise typer.Exit(code=1 if failed else 0)


@app.command("smoke")
def smoke_cmd(
    manifest: ManifestOpt,
    fixture: Annotated[Path, typer.Option("--fixture", help="Bronze fixture dir to run")],
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
) -> None:
    """ADR-025 upgrade gate: one fixture capture+process against this image, in a throwaway
    Postgres schema (or in memory without a DSN) and a throwaway Bronze; never production data."""
    m = _manifest(manifest)
    store: Store
    schema: str | None = None
    if dsn is None:
        typer.echo("smoke: no ENERGY_PLATFORM_DSN — pipeline only, in memory", err=True)
        store = MemoryStore()
    else:
        schema = f"smoke_{secrets.token_hex(4)}"
        try:
            create_schema(dsn, schema)
            upgrade(dsn, schema=schema)
            store = PostgresStore(dsn, schema=schema)
        except (StoreUnavailable, OSError, RuntimeError) as exc:
            typer.echo(f"smoke: cannot prepare schema {schema}: {exc}", err=True)
            drop_schema(dsn, schema)
            raise typer.Exit(code=1) from exc
    try:
        with _demo_bronze(bronze_dir) as bronze:
            report = smoke(m, fixture, store=store, bronze=bronze)
    finally:
        if isinstance(store, PostgresStore):
            store.close()
        if dsn is not None and schema is not None:
            drop_schema(dsn, schema)
    _echo(report)
    raise typer.Exit(code=0 if report.ok else 1)


@app.command("restore-drill")
def restore_drill_cmd(
    scratch_dsn: Annotated[
        str | None,
        typer.Option(
            "--scratch-dsn",
            envvar="ENERGY_PLATFORM_SCRATCH_DSN",
            help="the restored / empty PostgreSQL the ledger and Silver are rebuilt into",
        ),
    ] = None,
    scratch_schema: Annotated[
        str | None,
        typer.Option("--scratch-schema", help="rebuild into this schema of --scratch-dsn instead"),
    ] = None,
    manifests: Annotated[
        list[Path] | None, typer.Option("--manifest", "-m", help="manifest(s) to drill")
    ] = None,
    targets_root: TargetsRootOpt = TARGETS,
    replica_dir: Annotated[
        Path | None,
        typer.Option(
            "--replica-dir", help="replica Bronze directory (default: the S3 replica env)"
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="list and check, rebuild nothing")
    ] = False,
    dsn: DsnOpt = None,
) -> None:
    """ADR-002 restore drill: rebuild ledger + Silver from the replica Bronze into a scratch
    database and compare with live (ENERGY_PLATFORM_DSN, read-only). Exit 1 on any difference."""
    if not scratch_dsn:
        typer.echo(
            "restore-drill: --scratch-dsn or ENERGY_PLATFORM_SCRATCH_DSN is required", err=True
        )
        raise typer.Exit(code=1)
    paths = list(manifests or []) or [
        d / "manifest.yaml" for d in target_dirs(targets_root) if (d / "manifest.yaml").is_file()
    ]
    if not paths:
        typer.echo(f"restore-drill: no manifests under {targets_root} and none given", err=True)
        raise typer.Exit(code=1)
    loaded = [_manifest(p) for p in paths]
    if replica_dir is not None:
        replica = Bronze(FileBlobStore(replica_dir), FileCaptureLog(replica_dir))
    else:
        try:
            replica = replica_bronze_from_env(os.environ)
        except (BronzeConfigError, ObjectStoreError) as exc:
            typer.echo(f"restore-drill: replica: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    live: Store | None = None
    if dsn:
        live = _store(dsn, required=True)
    if scratch_schema is not None and dry_run:
        typer.echo(
            f"restore-drill: dry run — schema {scratch_schema} would be created and migrated; "
            "checking the scratch server only",
            err=True,
        )
        scratch_schema = None
    if scratch_schema is not None:
        create_schema(scratch_dsn, scratch_schema)
    try:
        if not dry_run:
            upgrade(scratch_dsn, schema=scratch_schema)
        scratch: Store = PostgresStore(scratch_dsn, schema=scratch_schema)
    except (StoreUnavailable, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"restore-drill: scratch: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    report = restore_drill(loaded, scratch=scratch, replica=replica, live=live, dry_run=dry_run)
    _echo(report)
    typer.echo(
        f"restore-drill: {'OK' if report.ok else 'FAILED'} in {report.seconds:.1f}s", err=True
    )
    raise typer.Exit(code=0 if report.ok else 1)


@app.command("storage-probe")
def storage_probe_cmd(
    storage_class: Annotated[
        str | None,
        typer.Option(
            "--storage-class",
            envvar="ENERGY_PLATFORM_S3_STORAGE_CLASS",
            help="the class bronze.tiering.lifecycle would transition to",
        ),
    ] = None,
) -> None:
    """ADR-021 §3: PUT one object with the class and HEAD it back; exit 1 unless the gateway
    reports exactly that class. Store from the ENERGY_PLATFORM_S3_* environment (P5-D4)."""
    if not storage_class:
        typer.echo("storage-probe: --storage-class or ENERGY_PLATFORM_S3_STORAGE_CLASS", err=True)
        raise typer.Exit(code=1)
    try:
        store = object_store_from_env(os.environ)
    except (BronzeConfigError, ObjectStoreError) as exc:
        typer.echo(f"storage-probe: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    report = storage_probe(store, storage_class)
    _echo(report)
    raise typer.Exit(code=0 if report.ok else 1)


@app.command("process")
def process_cmd(manifest: ManifestOpt, dsn: DsnOpt = None, bronze_dir: BronzeOpt = None) -> None:
    """Reconcile, then claim and process every pending capture under a fence (ADR-024 §4)."""
    rt = _runtime(
        _manifest(manifest), _store(dsn, required=True), _bronze(bronze_dir), _live_fetcher
    )
    for report in process(rt):
        _echo(report)


@app.command("replay")
def replay_cmd(
    manifest: ManifestOpt,
    since: Annotated[str | None, typer.Option("--from")] = None,
    until: Annotated[str | None, typer.Option("--to")] = None,
    derivation: Annotated[
        str | None, typer.Option("--derivation", help="ADR-016 §4 repair")
    ] = None,
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
) -> None:
    """Enqueue replays of existing captures; never fetches. Then run `process`."""
    rt = _runtime(
        _manifest(manifest), _store(dsn, required=True), _bronze(bronze_dir), _live_fetcher
    )
    if derivation is not None:
        queued = replay_derivation(rt, derivation)
    elif since is not None and until is not None:
        queued = replay_range(rt, _instant(since), _instant(until))
    else:
        typer.echo("give --from and --to, or --derivation", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"queued {len(queued)} replay attempt(s)")
    for attempt in queued:
        _echo(attempt)


@app.command("backfill")
def backfill_cmd(
    manifest: ManifestOpt,
    live: Annotated[bool, typer.Option("--live", help="fetch from the source (opt-in)")] = False,
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="at most N fetches (the CronJob's bound)")
    ] = None,
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
) -> None:
    """Fetch every run the gap detector marked missing_capture (within history.max_age)."""
    if not live:
        typer.echo("backfill fetches from the source: pass --live to confirm", err=True)
        raise typer.Exit(code=1)
    rt = _runtime(
        _manifest(manifest), _store(dsn, required=True), _bronze(bronze_dir), _live_fetcher
    )
    for report in backfill(rt, limit=limit):
        _echo(report)


@app.command("gaps")
def gaps_cmd(
    manifest: Annotated[
        Path | None, typer.Option("--manifest", "-m", help="path to a manifest.yaml")
    ] = None,
    all_targets: Annotated[
        bool, typer.Option("--all", help="every target under --targets-root (the CronJob)")
    ] = False,
    targets_root: TargetsRootOpt = TARGETS,
    lookback_hours: Annotated[int, typer.Option("--lookback-hours")] = 48,
    with_freshness: Annotated[
        bool, typer.Option("--with-freshness", help="then write the ADR-037 freshness row")
    ] = False,
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
) -> None:
    """Classify expected instants: pending, unprocessed_capture, missing_capture, unrecoverable."""
    if (manifest is None) == (not all_targets):
        typer.echo("choose exactly one of --manifest PATH or --all", err=True)
        raise typer.Exit(code=1)
    paths = (
        [manifest]
        if manifest is not None
        else [
            d / "manifest.yaml"
            for d in target_dirs(targets_root)
            if (d / "manifest.yaml").is_file()
        ]
    )
    store = _store(dsn, required=True)
    bronze = _bronze(bronze_dir)
    for path in paths:
        rt = _runtime(_manifest(path), store, bronze, _live_fetcher)
        for gap in detect_gaps(rt, lookback=timedelta(hours=lookback_hours)):
            _echo(gap)
        if with_freshness:
            _echo(record_freshness(rt))


@app.command("freshness")
def freshness_cmd(manifest: ManifestOpt, dsn: DsnOpt = None, bronze_dir: BronzeOpt = None) -> None:
    """Compute and store the target's freshness row (ADR-037 / ADR-012; 01 §5 states)."""
    rt = _runtime(
        _manifest(manifest), _store(dsn, required=True), _bronze(bronze_dir), _live_fetcher
    )
    _echo(record_freshness(rt))


# ---------------------------------------------------------------------------- harness (Phase 3)


@app.command("new-target")
def new_target(
    target_id: TargetArg,
    modality: Annotated[
        str,
        typer.Option(
            "--modality", help="soap-xml | dated-file | html-table | rest-json | rest-xml"
        ),
    ],
    dataset: Annotated[
        str | None, typer.Option("--dataset", help="registered dataset_id to fill from")
    ] = None,
    host: Annotated[str, typer.Option("--host", help="the source hostname")] = "replace-me.example",
    with_parser: Annotated[bool, typer.Option("--with-parser", help="add a parser.py")] = False,
    targets_root: TargetsRootOpt = TARGETS,
) -> None:
    """Scaffold exactly the ADR-027 surface; it is not a target until the placeholders are gone."""
    if modality not in ("soap-xml", "dated-file", "html-table", "rest-json", "rest-xml"):
        typer.echo(f"unknown modality {modality!r}", err=True)
        raise typer.Exit(code=1)
    mod = cast(Modality, modality)
    try:
        result = scaffold_target(
            targets_root, target_id, mod, dataset_id=dataset, host=host, with_parser=with_parser
        )
    except ScaffoldError as exc:
        typer.echo(f"new-target: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for path in result.files:
        typer.echo(f"wrote {path}")
    typer.echo(f"next: fill REPLACE_ME in {result.target / 'manifest.yaml'}, then")
    typer.echo(f"      energyctl validate {target_id}")
    if result.admission_required:
        typer.echo(
            "      the dataset is not registered: energyctl admission-request "
            f"{target_id} (ADR-022 Route B)"
        )


@app.command("record-fixture")
def record_fixture(
    target_id: TargetArg,
    name: Annotated[str, typer.Option("--name", help="fixture name, e.g. ordinary_day")],
    live: Annotated[bool, typer.Option("--live", help="fetch from the source (opt-in)")] = False,
    from_file: Annotated[
        Path | None, typer.Option("--from-file", help="wrap a saved payload offline")
    ] = None,
    scheduled_for: Annotated[
        str | None, typer.Option("--scheduled-for", help="ISO 8601 instant with offset")
    ] = None,
    content_type: Annotated[str | None, typer.Option("--content-type")] = None,
    targets_root: TargetsRootOpt = TARGETS,
) -> None:
    """Write targets/<id>/fixtures/<name>/ as a Bronze object (blob + entry.json; ADR-020)."""
    if live == (from_file is not None):
        typer.echo("choose exactly one of --live or --from-file PATH", err=True)
        raise typer.Exit(code=1)
    target, m = _target_manifest(targets_root, target_id)
    when = _instant(scheduled_for) if scheduled_for else None
    try:
        if from_file is not None:
            entry = record_from_file(
                target, m, name, from_file, scheduled_for=when, content_type=content_type
            )
        else:
            entry = record_live(target, m, name, scheduled_for=when)
    except (FixtureError, OSError, FileNotFoundError) as exc:
        typer.echo(f"record-fixture: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _echo(entry)


@app.command("run-target-tests")
def run_target_tests_cmd(target_id: TargetArg, targets_root: TargetsRootOpt = TARGETS) -> None:
    """Surface rules, every golden through the platform, then the target's own pytest module."""
    target, _ = _target_manifest(targets_root, target_id)
    report = run_target_tests(target)
    for line in report.lines():
        typer.echo(line)
    if report.pytest_output:
        typer.echo(report.pytest_output.rstrip())
    raise typer.Exit(code=0 if report.ok else 1)


@app.command("admission-request")
def admission_request(
    target_id: TargetArg,
    out_dir: Annotated[Path, typer.Option("--out", help="docs/admissions/")] = Path(
        "docs/admissions"
    ),
    targets_root: TargetsRootOpt = TARGETS,
) -> None:
    """Route B (ADR-022): write docs/admissions/<id>.md listing exactly what is unregistered."""
    _, m = _target_manifest(targets_root, target_id)
    result = validate_manifest(m)
    path = write_request(m, out_dir)
    typer.echo(f"wrote {path} ({result.status})")
    if result.status == "OK":
        typer.echo("nothing is missing: this target can go Route A", err=True)


@app.command("pr-bundle")
def pr_bundle(
    target_id: TargetArg,
    outbox: Annotated[Path, typer.Option("--outbox", help="where bundles go")] = Path(
        ".energy_platform/outbox"
    ),
    title: Annotated[str | None, typer.Option("--title")] = None,
    repo: Annotated[Path, typer.Option("--repo", help="repository root")] = Path("."),
) -> None:
    """Prepare a Route A pull request bundle (all gates green, one target) — never pushes."""
    try:
        bundle = prepare_bundle(repo, target_id, outbox, title=title)
    except BundleRefused as exc:
        typer.echo(f"pr-bundle: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote {bundle.path} ({len(bundle.files)} files, branch {bundle.branch})")
    typer.echo(f"next: python -m scripts.apply_pr_bundle {bundle.path} && gh pr create")


@app.command("mcp-serve")
def mcp_serve(
    repo: Annotated[Path, typer.Option("--root", help="repository root")] = Path("."),
    outbox: Annotated[Path, typer.Option("--outbox")] = Path(".energy_platform/outbox"),
    allow_network: Annotated[
        bool, typer.Option("--allow-network", help="let record_fixture fetch (opt-in)")
    ] = False,
) -> None:
    """Serve the ADR-007 tools over stdio (JSON-RPC 2.0); the CLI and CI share the library."""
    raise typer.Exit(code=serve_stdio(repo, outbox, allow_network=allow_network))


# ---------------------------------------------------------------------------- demo


@contextmanager
def _demo_bronze(bronze_dir: Path | None) -> Iterator[Bronze]:
    if bronze_dir is not None:
        yield _bronze(bronze_dir)
        return
    with tempfile.TemporaryDirectory(prefix="energy-platform-demo-") as tmp:
        yield _bronze(Path(tmp))


@app.command()
def demo(
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
    examples: Annotated[Path, typer.Option("--examples", help="examples/ directory")] = EXAMPLES,
) -> None:
    """Fixture → capture → Bronze → parse → map → Postgres → query, offline (ADR-010)."""
    if dsn is None:
        typer.echo("demo needs PostgreSQL: run `make demo` or set ENERGY_PLATFORM_DSN", err=True)
        raise typer.Exit(code=1)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    typer.echo("== migrate (every migration has a downgrade, ADR-016 §3)")
    upgrade(dsn)
    store = _store(dsn, required=True)
    with _demo_bronze(bronze_dir) as bronze:
        for target in DEMO_TARGETS:
            m = _manifest(examples / "manifests" / f"{target}.yaml")
            entry, payload = load_fixture(examples / "fixtures" / target)
            rt = _runtime(m, store, bronze, _fixture_factory(payload, entry.content_type))
            typer.echo(f"\n== {target}: validate")
            _echo(validate_manifest(m))
            typer.echo(f"== {target}: capture (fixture through the real fetch path, offline)")
            report = capture(rt, entry.scheduled_for)
            _echo(report)
            typer.echo(f"== {target}: process (reconcile → claim → decode → map → fenced commit)")
            for p in process(rt):
                _echo(p)
            typer.echo(f"== {target}: replay of the same capture is a no-op (ADR-023 proof 1)")
            replay_range(
                rt,
                entry.scheduled_for - timedelta(minutes=1),
                entry.scheduled_for + timedelta(minutes=1),
            )
            for p in process(rt):
                _echo(p)
        typer.echo("\n== query: observations_current per dataset")
        for dataset_id in ("ote.idm_continuous", "ceps.load"):
            rows = store.current_rows(dataset_id)
            metrics = sorted({r.observation.metric for r in rows})
            typer.echo(f"{dataset_id}: {len(rows)} current rows, metrics {metrics}")
            for row in rows[:3]:
                o = row.observation
                typer.echo(
                    f"  {o.delivery_start_utc:%Y-%m-%dT%H:%MZ} {o.metric}={o.value} {o.unit} "
                    f"via {o.source_transport} (basis {row.ordering_basis}, "
                    f"derivation {o.derivation_id})"
                )
        typer.echo("\n== quality events")
        for event in store.quality_events():
            typer.echo(f"  {event.target_id} {event.kind} [{event.severity}] {event.message}")
    typer.echo("\ndemo: OK")


if __name__ == "__main__":
    app()
