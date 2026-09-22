"""``restore-drill``: prove the backups by rebuilding from them (ADR-002, ADR-024 §2, ADR-021 §5).

Given a **scratch** store (a freshly restored or empty Postgres), the **replica** Bronze (store B,
ADR-036 §5) and, for comparison, the **live** store: for every committed target the drill
rebuilds the ledger by ``reconcile`` over the full replica history, processes every run (the
replay reads blobs from the replica, which is the cold-backed read path), then compares with
live: runs that reached ``processed``, current Silver rows for the target's transport and an
order-independent checksum over (observation identity, value). Any difference fails the drill.
``dry_run`` only lists what the full drill would touch and checks both stores answer. Wall clock
is reported: that number is the RTO figure the runbook quotes, never an assumption.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from energy_platform.bronze import Bronze
from energy_platform.contracts.manifest import Manifest
from energy_platform.contracts.observation import observation_identity
from energy_platform.fetch import Fetcher
from energy_platform.runtime.context import Runtime, utc_now
from energy_platform.runtime.process import process
from energy_platform.runtime.reconcile import reconcile
from energy_platform.store import Store, StoreUnavailable


@dataclass(frozen=True, slots=True)
class SilverDigest:
    rows: int
    checksum: str


@dataclass(frozen=True, slots=True)
class TargetDrillReport:
    target_id: str
    replica_entries: int
    scratch_processed: int
    live_processed: int | None
    scratch: SilverDigest | None
    live: SilverDigest | None
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class DrillReport:
    ok: bool
    dry_run: bool
    started_at: datetime
    finished_at: datetime
    targets: tuple[TargetDrillReport, ...]

    @property
    def seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


def _never_fetch(manifest: Manifest) -> Fetcher:
    raise RuntimeError(f"{manifest.target_id}: the restore drill never fetches (ADR-004 replay)")


def silver_digest(store: Store, manifest: Manifest) -> SilverDigest:
    rows = store.current_rows(
        manifest.contract.dataset_id, transport=manifest.contract.source_transport
    )
    lines = sorted(f"{observation_identity(r.observation)!r}|{r.value}" for r in rows)
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return SilverDigest(len(rows), digest)


def _processed(store: Store, target_id: str) -> int:
    return Counter(r.state for r in store.runs(target_id))["processed"]


def _drill_target(
    manifest: Manifest,
    *,
    live: Store | None,
    scratch: Store,
    replica: Bronze,
    clock: Callable[[], datetime],
    owner: str,
    dry_run: bool,
) -> TargetDrillReport:
    target = manifest.target_id
    entries = len(replica.log.list(target))
    rt = Runtime(
        manifest=manifest,
        bronze=replica,
        store=scratch,
        fetcher_factory=_never_fetch,
        clock=clock,
        owner=owner,
    )
    if dry_run:
        try:
            scratch.runs(target)
            live_ok = live is None or live.runs(target) is not None
        except StoreUnavailable as exc:
            return TargetDrillReport(target, entries, 0, None, None, None, False, f"store: {exc}")
        return TargetDrillReport(
            target, entries, 0, None, None, None, live_ok, f"dry run: {entries} replica entries"
        )
    try:
        reconciled = reconcile(rt, window=None)
        reports = process(rt)
    except StoreUnavailable as exc:
        return TargetDrillReport(target, entries, 0, None, None, None, False, f"store: {exc}")
    failed = [r for r in reports if r.outcome not in {"ok", "noop"}]
    scratch_digest = silver_digest(scratch, manifest)
    scratch_processed = _processed(scratch, target)
    if live is None:
        ok = not failed
        return TargetDrillReport(
            target,
            entries,
            scratch_processed,
            None,
            scratch_digest,
            None,
            ok,
            f"rebuilt {len(reconciled)} runs, {len(reports)} processed, {len(failed)} failed "
            f"(no live store to compare)",
        )
    live_digest = silver_digest(live, manifest)
    live_processed = _processed(live, target)
    problems = []
    if failed:
        problems.append(f"{len(failed)} run(s) failed to process from the replica")
    if scratch_processed != live_processed:
        problems.append(f"processed runs {scratch_processed} != live {live_processed}")
    if scratch_digest != live_digest:
        problems.append(
            f"silver rows {scratch_digest.rows} != live {live_digest.rows}"
            if scratch_digest.rows != live_digest.rows
            else "silver checksum differs at equal row count"
        )
    return TargetDrillReport(
        target,
        entries,
        scratch_processed,
        live_processed,
        scratch_digest,
        live_digest,
        not problems,
        "; ".join(problems) if problems else f"identical: {live_digest.rows} rows",
    )


def restore_drill(
    manifests: Iterable[Manifest],
    *,
    scratch: Store,
    replica: Bronze,
    live: Store | None = None,
    clock: Callable[[], datetime] = utc_now,
    owner: str = "restore-drill",
    dry_run: bool = False,
) -> DrillReport:
    started = clock()
    targets = tuple(
        _drill_target(
            m,
            live=live,
            scratch=scratch,
            replica=replica,
            clock=clock,
            owner=owner,
            dry_run=dry_run,
        )
        for m in manifests
    )
    finished = clock()
    return DrillReport(all(t.ok for t in targets), dry_run, started, finished, targets)
