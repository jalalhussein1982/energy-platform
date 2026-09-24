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


Fingerprint = bytes
"""16 bytes per Silver version: blake2b over (observation identity, payload sha256, derivation
id, value). The comparison keeps one fingerprint per version and never the rows themselves, so
the drill's memory is a few dozen bytes per version whatever the dataset holds (2026-09-24: the
first scheduled drill on the demo was OOM-killed at 512 MiB holding ~75 000 rows as objects,
three times over)."""


def _fingerprint(o: Any) -> Fingerprint:
    line = f"{observation_identity(o)!r}|{o.payload_sha256}|{o.derivation_id}|{o.value!s}"
    return hashlib.blake2b(line.encode(), digest_size=16).digest()


def silver_fingerprints(store: Store, manifest: Manifest) -> set[Fingerprint]:
    """Every stored Silver version this target's transport produced, as fingerprints. Versions
    are a pure function of Bronze + derivation, so a rebuild from the replica must reproduce
    each of them; the current view is not compared because which transport wins a shared
    identity may depend on processing order (ADR-023 §3 tie-break), and live may lag the
    rebuild on pending captures. Rows are streamed (``Store.iter_rows``), never materialised."""
    dataset_id = manifest.contract.dataset_id
    transport = manifest.contract.source_transport
    rows = store.iter_rows(dataset_id, transport=transport)
    return {_fingerprint(row.observation) for row in rows}


def _digest(fingerprints: set[Fingerprint]) -> SilverDigest:
    h = hashlib.sha256()
    for fp in sorted(fingerprints):
        h.update(fp)
    return SilverDigest(len(fingerprints), h.hexdigest())


def silver_digest(store: Store, manifest: Manifest) -> SilverDigest:
    return _digest(silver_fingerprints(store, manifest))


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
        # the scratch server was reached when its Store was built (a fresh cluster may hold no
        # tables yet); live is read to prove the comparison side answers
        try:
            live_processed = None if live is None else _processed(live, target)
        except StoreUnavailable as exc:
            return TargetDrillReport(target, entries, 0, None, None, None, False, f"store: {exc}")
        return TargetDrillReport(
            target,
            entries,
            0,
            live_processed,
            None,
            None,
            True,
            f"dry run: {entries} replica entries; scratch server reachable",
        )
    try:
        reconciled = reconcile(rt, window=None)
        reports = process(rt)
    except StoreUnavailable as exc:
        return TargetDrillReport(target, entries, 0, None, None, None, False, f"store: {exc}")
    failed = [r for r in reports if r.outcome not in {"ok", "noop"}]
    scratch_fp = silver_fingerprints(scratch, manifest)
    scratch_digest = _digest(scratch_fp)
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
    live_fp = silver_fingerprints(live, manifest)
    live_digest = _digest(live_fp)
    live_processed = _processed(live, target)
    # a version live holds with a value the rebuild does not reproduce is missing (data loss);
    # the fingerprint carries the value, so a diverging value is a missing version, not a match
    missing = len(live_fp - scratch_fp)
    extra = len(scratch_fp - live_fp)
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
            f"live ⊆ rebuild: {len(live_fp)} versions reproduced; the rebuild is ahead by "
            f"{extra} (live has captures it has not processed yet)"
        )
    else:
        message = f"identical: {len(live_fp)} Silver versions"
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
