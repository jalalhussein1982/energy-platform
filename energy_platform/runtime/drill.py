"""``restore-drill``: prove the backups by rebuilding from them (ADR-002, ADR-024 §2, ADR-021 §5).

Given a **scratch** store (a freshly restored or empty Postgres), the **replica** Bronze (store B,
ADR-036 §5) and, for comparison, the **live** store: for every committed target the drill
rebuilds the ledger by ``reconcile`` over the full replica history, processes every run (the
replay reads blobs from the replica, which is the cold-backed read path), then compares with
live: the rebuild must hold at least as many ``processed`` runs and every Silver **version**
(observation identity + payload + derivation → value) live holds for the target's transport —
live ⊆ rebuild. The rebuild may be ahead (live still has pending captures); a version live
holds that the rebuild lacks is data loss and fails the drill.
``dry_run`` only lists what the full drill would touch and checks both stores answer. Wall clock
is reported: that number is the RTO figure the runbook quotes, never an assumption.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    """Silver versions: every stored version of this transport's rows, not the current view."""
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
    missing_versions: int = 0
    """Silver versions live holds that the rebuild does not: the only data-loss signal."""
    extra_versions: int = 0
    """Versions the rebuild has and live does not yet (live has pending captures): informational."""


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


VersionKey = tuple[Any, str, str]


def silver_versions(store: Store, manifest: Manifest) -> dict[VersionKey, str]:
    """Every stored Silver version this target's transport produced, keyed by
    (observation identity, payload sha256, derivation id) → value. Versions are a pure function
    of Bronze + derivation, so a rebuild from the replica must reproduce each of them; the
    current view is not compared because which transport wins a shared identity may depend on
    processing order (ADR-023 §3 tie-break), and live may lag the rebuild on pending captures."""
    transport = manifest.contract.source_transport
    versions: dict[VersionKey, str] = {}
    for row in store.all_rows(manifest.contract.dataset_id):
        o = row.observation
        if o.source_transport != transport:
            continue
        versions[(observation_identity(o), o.payload_sha256, o.derivation_id)] = str(o.value)
    return versions


def silver_digest(store: Store, manifest: Manifest) -> SilverDigest:
    versions = silver_versions(store, manifest)
    lines = sorted(f"{key!r}|{value}" for key, value in versions.items())
    return SilverDigest(len(versions), hashlib.sha256("\n".join(lines).encode()).hexdigest())


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
    live_versions = silver_versions(live, manifest)
    scratch_versions = silver_versions(scratch, manifest)
    live_digest = silver_digest(live, manifest)
    live_processed = _processed(live, target)
    missing = sum(1 for k, v in live_versions.items() if scratch_versions.get(k) != v)
    extra = sum(1 for k in scratch_versions if k not in live_versions)
    problems = []
    if failed:
        problems.append(f"{len(failed)} run(s) failed to process from the replica")
    if scratch_processed < live_processed:
        problems.append(f"processed runs {scratch_processed} < live {live_processed}")
    if missing:
        problems.append(f"{missing} Silver version(s) live holds are missing from the rebuild")
    if problems:
        message = "; ".join(problems)
    elif extra:
        message = (
            f"live ⊆ rebuild: {len(live_versions)} versions reproduced; the rebuild is ahead by "
            f"{extra} (live has captures it has not processed yet)"
        )
    else:
        message = f"identical: {len(live_versions)} Silver versions"
    return TargetDrillReport(
        target,
        entries,
        scratch_processed,
        live_processed,
        scratch_digest,
        live_digest,
        not problems,
        message,
        missing_versions=missing,
        extra_versions=extra,
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
