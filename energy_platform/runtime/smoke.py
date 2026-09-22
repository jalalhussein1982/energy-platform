"""``smoke``: the ADR-025 upgrade gate — one fixture capture + process against *this* image.

The smoke never touches production data: it runs against a **fresh** Bronze (a temporary
directory) and a store the caller isolated (a throwaway Postgres schema, or ``MemoryStore`` when
no database is configured). It asserts that the run ends ``processed`` and that at least one
Silver row exists for the manifest's dataset; anything else — a fetch-path error, a decode or
parse failure, quarantine, a store outage — is a failed gate and the reason is in ``message``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from energy_platform.bronze import Bronze, BronzeError, load_fixture
from energy_platform.contracts.manifest import Manifest
from energy_platform.fetch import Fetcher, FixtureTransport
from energy_platform.runtime.capture import capture
from energy_platform.runtime.context import Runtime, utc_now
from energy_platform.runtime.process import process
from energy_platform.store import Store, StoreUnavailable


@dataclass(frozen=True, slots=True)
class SmokeReport:
    ok: bool
    target_id: str
    scheduled_for: datetime | None
    run_state: str | None
    silver_rows: int
    message: str


def fixture_fetcher_factory(
    payload: bytes, content_type: str | None = None
) -> Callable[[Manifest], Fetcher]:
    """A fetcher that answers every request with the fixture payload, offline (ADR-010)."""

    def factory(manifest: Manifest) -> Fetcher:
        return Fetcher(
            allowed_hosts=manifest.allowed_hosts,
            allow_insecure=manifest.allow_insecure,
            transport=FixtureTransport(
                payload, content_type=content_type or "application/octet-stream"
            ),
            offline=True,
            sleep=lambda _: None,
        )

    return factory


def smoke(
    manifest: Manifest,
    fixture_dir: Path,
    *,
    store: Store,
    bronze: Bronze,
    clock: Callable[[], datetime] = utc_now,
    owner: str = "smoke",
) -> SmokeReport:
    target = manifest.target_id
    try:
        entry, payload = load_fixture(fixture_dir)
    except (BronzeError, OSError, ValueError) as exc:
        return SmokeReport(False, target, None, None, 0, f"fixture unreadable: {exc}")
    rt = Runtime(
        manifest=manifest,
        bronze=bronze,
        store=store,
        fetcher_factory=fixture_fetcher_factory(payload, entry.content_type),
        clock=clock,
        owner=owner,
    )
    when = entry.scheduled_for
    cap = capture(rt, when, force=True)
    if cap.outcome != "ok":
        return SmokeReport(False, target, when, None, 0, f"capture {cap.outcome}: {cap.error}")
    if not cap.ledger_updated:
        return SmokeReport(False, target, when, None, 0, "ledger unavailable: capture not acked")
    try:
        reports = process(rt)
    except StoreUnavailable as exc:
        return SmokeReport(False, target, when, None, 0, f"store unavailable: {exc}")
    mine = [r for r in reports if r.scheduled_for == when]
    if not mine:
        return SmokeReport(False, target, when, None, 0, "process claimed nothing for the run")
    run = store.get_run(target, when)
    state = run.state if run is not None else None
    rows = len(store.current_rows(manifest.contract.dataset_id))
    if mine[-1].outcome != "ok" or state != "processed":
        return SmokeReport(
            False, target, when, state, rows, f"process {mine[-1].outcome}: {mine[-1].error}"
        )
    if rows < 1:
        return SmokeReport(False, target, when, state, rows, "no Silver row for the dataset")
    return SmokeReport(True, target, when, state, rows, f"processed; {rows} Silver rows")
