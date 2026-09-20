"""``energyctl``: a thin client of the library (ADR-000). Phase 2 verbs take ``--manifest``.

Persistence is PostgreSQL through ``--dsn`` / ``ENERGY_PLATFORM_DSN``; Bronze is a directory
through ``--bronze-dir`` / ``ENERGY_PLATFORM_BRONZE_DIR``. ``capture`` works without a database
(ADR-024 §1). Live fetching is opt-in (``--live``); ``--fixture`` replays a Bronze fixture
through the real fetch path with an offline transport (ADR-010).
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from energy_platform.bronze import Bronze, FileBlobStore, FileCaptureLog, load_fixture
from energy_platform.contracts.manifest import (
    Manifest,
    ManifestSyntaxError,
    load_manifest,
    validate_manifest,
)
from energy_platform.fetch import EnvSecretResolver, Fetcher, FixtureTransport
from energy_platform.runtime import (
    Runtime,
    backfill,
    capture,
    detect_gaps,
    process,
    replay_derivation,
    replay_range,
)
from energy_platform.silver import downgrade, upgrade
from energy_platform.store import Store, StoreUnavailable
from energy_platform.store.postgres import PostgresStore
from energy_platform.store.unavailable import UnavailableStore

app = typer.Typer(
    name="energyctl",
    help="energy-platform command line (Phase 2: validate, capture, process, replay, gaps, demo)",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

ManifestOpt = Annotated[Path, typer.Option("--manifest", "-m", help="path to a manifest.yaml")]
DsnOpt = Annotated[
    str | None,
    typer.Option("--dsn", envvar="ENERGY_PLATFORM_DSN", help="PostgreSQL DSN (>= 16, ADR-030)"),
]
BronzeOpt = Annotated[
    Path | None,
    typer.Option(
        "--bronze-dir",
        envvar="ENERGY_PLATFORM_BRONZE_DIR",
        help="Bronze directory (blobs + capture log)",
    ),
]

EXAMPLES = Path("examples")
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
    root = bronze_dir or Path(".bronze")
    return Bronze(FileBlobStore(root), FileCaptureLog(root))


def _live_fetcher(manifest: Manifest) -> Fetcher:
    return Fetcher(allowed_hosts=manifest.allowed_hosts, allow_insecure=manifest.allow_insecure)


def _fixture_factory(payload: bytes, content_type: str | None = None) -> Any:
    def factory(manifest: Manifest) -> Fetcher:
        return Fetcher(
            allowed_hosts=manifest.allowed_hosts,
            allow_insecure=manifest.allow_insecure,
            transport=FixtureTransport(
                payload, content_type=content_type or "application/octet-stream"
            ),
            offline=True,
        )

    return factory


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


@app.command()
def validate(manifest: ManifestOpt) -> None:
    """Structural + admission validation; exit 0 OK, 1 INVALID, 2 ADMISSION_REQUIRED."""
    result = validate_manifest(_manifest(manifest))
    _echo(result)
    raise typer.Exit(code={"OK": 0, "INVALID": 1, "ADMISSION_REQUIRED": 2}[result.status])


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
        factory = _fixture_factory(payload, entry.content_type)
    else:
        when = _instant(scheduled_for) if scheduled_for else datetime.now(UTC)
        factory = _live_fetcher
    rt = _runtime(m, _store(dsn, required=False), _bronze(bronze_dir), factory)
    report = capture(rt, when, force=force)
    _echo(report)
    raise typer.Exit(code=0 if report.outcome in {"ok", "noop"} else 1)


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
    for report in backfill(rt):
        _echo(report)


@app.command("gaps")
def gaps_cmd(
    manifest: ManifestOpt,
    lookback_hours: Annotated[int, typer.Option("--lookback-hours")] = 48,
    dsn: DsnOpt = None,
    bronze_dir: BronzeOpt = None,
) -> None:
    """Classify expected instants: pending, unprocessed_capture, missing_capture, unrecoverable."""
    rt = _runtime(
        _manifest(manifest), _store(dsn, required=True), _bronze(bronze_dir), _live_fetcher
    )
    for gap in detect_gaps(rt, lookback=timedelta(hours=lookback_hours)):
        _echo(gap)


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
