"""``restore-drill``: prove the backups by rebuilding from them (ADR-002, ADR-024 §2, ADR-021 §5,
ADR-036 amendment 5).

Given a **scratch** store (a freshly restored or empty Postgres), the **replica** Bronze (store B,
ADR-036 §5) and, for comparison, the **live** store: the drill first rebuilds **every** committed
target in the scratch store — ``reconcile`` over the full replica history, then ``process`` of
every run, **every distinct capture of a run, oldest first**, because a correction that found
changed content is a new capture and live keeps the version each capture produced — and only
then compares each target with live. Two targets can share a dataset and a transport (the
committed settlement targets do), so comparing one before its siblings are rebuilt read the
siblings' rows as loss (review 3 R5); every comparison is scoped to the target's **own lineage**,
the rows its own attempts produced, and a version the rebuild attributed to a sibling counts as
reproduced.

**What the rebuild guarantees (ADR-036 amendment 5, review 3 R6): values, not derivation ids.**
Per (observation identity, payload) live holds within the replica bound, the rebuild must
reproduce the value of live's *newest* derivation for that pair. A pair the rebuild lacks is
``missing`` (loss); a pair whose value differs is ``diverging`` — the running implementation no
longer produces live's value from that payload: an un-replayed correction or a regression, and
the drill fails on it; versions under retired derivations are ``historical`` — counted and
named, not compared, because old code is not in the replica; the physical backup keeps them and
the drill's first phase (against the restored database) proves that backup. The rebuild may be
ahead (live still has pending captures).

The comparison is bounded by the **replica's newest capture instant** for the target, read
from a snapshot of the replica's log taken **before** the target's rebuild and kept for its
comparison: a live capture fetched after it cannot be in the replica yet (replication runs on
its own cadence), so its versions and its run are not compared and are reported as lagging; a
live capture fetched before it existed when the replica was last synced, so its absence is
loss. A capture replication lands between the rebuild and the comparison is beyond the
snapshot — lag, never loss.
``dry_run`` only lists what the full drill would touch and checks both stores answer. Wall clock
is reported: that number is the RTO figure the runbook quotes, never an assumption.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from energy_platform.bronze import Bronze
from energy_platform.bronze.capture_log import CaptureEntry
from energy_platform.contracts.manifest import Manifest
from energy_platform.contracts.observation import observation_identity
from energy_platform.fetch import Fetcher
from energy_platform.parse import parser_ref
from energy_platform.runtime.context import Runtime, utc_now
from energy_platform.runtime.process import ProcessReport, process, process_one
from energy_platform.runtime.reconcile import reconcile
from energy_platform.store import Store, StoredObservation, StoreUnavailable, derivation_for


@dataclass(frozen=True, slots=True)
class SilverDigest:
    rows: int
    """Silver versions compared: the target's own, one per (identity, payload, value)."""
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
    """(identity, payload) pairs live holds that the rebuild does not: the loss signal."""
    extra_versions: int = 0
    """Versions the rebuild has and live does not yet (live has pending captures): informational."""
    lagging_runs: int = 0
    """Live runs whose capture is newer than the replica's newest and not in it: not compared."""
    diverging_versions: int = 0
    """Pairs the rebuild reproduces with another value than live's newest derivation: the
    running implementation disagrees with live (an un-replayed correction, or a regression)."""
    historical_versions: int = 0
    """Live versions under a derivation a newer one superseded for the same pair: not compared
    (ADR-036 amendment 5 — old code is not in the replica; the physical backup keeps them)."""
    historical_derivations: int = 0
    sibling_versions: int = 0
    """Versions the rebuild attributed to a sibling target sharing the dataset and transport."""


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
"""16 bytes per Silver version: blake2b over (observation identity, payload sha256, value) —
the derivation id is deliberately absent (ADR-036 amendment 5). The comparison keeps one
fingerprint per version and never the rows themselves, so the drill's memory is a few dozen
bytes per version whatever the dataset holds (2026-09-24: the first scheduled drill on the demo
was OOM-killed at 512 MiB holding ~75 000 rows as objects, three times over)."""

PairKey = bytes
"""16 bytes per (observation identity, payload sha256): what a version is *of*."""

_EPOCH = datetime.min.replace(tzinfo=UTC)


def _pair(o: Any) -> PairKey:
    line = f"{observation_identity(o)!r}|{o.payload_sha256}"
    return hashlib.blake2b(line.encode(), digest_size=16).digest()


def _fingerprint(o: Any) -> Fingerprint:
    line = f"{observation_identity(o)!r}|{o.payload_sha256}|{o.value!s}"
    return hashlib.blake2b(line.encode(), digest_size=16).digest()


def _invalidated(store: Store, target_id: str) -> Callable[[int, str], bool]:
    """``(run_attempt id, derivation id) → produced by an invalidated capture`` (ADR-038): one
    read of the target's invalidations and attempts, then a local check per row."""
    decisions = {(i.capture_id, i.derivation_id) for i in store.invalidations(target_id)}
    if not decisions:
        return lambda attempt_id, derivation_id: False
    captures = store.attempt_captures(target_id)

    def check(attempt_id: int, derivation_id: str) -> bool:
        capture_id = captures.get(attempt_id)
        return capture_id is not None and (
            (capture_id, None) in decisions or (capture_id, derivation_id) in decisions
        )

    return check


def _own_rows(store: Store, manifest: Manifest) -> Iterator[StoredObservation]:
    """The target's own valid Silver versions, streamed (``Store.iter_rows``, never
    materialised): rows of the dataset and transport that one of the target's own attempts
    produced (lineage; review 3 R5) and that no invalidated capture produced (ADR-038)."""
    target = manifest.target_id
    lineage = set(store.attempt_captures(target))
    voided = _invalidated(store, target)
    for row in store.iter_rows(
        manifest.contract.dataset_id, transport=manifest.contract.source_transport
    ):
        if row.run_attempt_id not in lineage:
            continue
        if voided(row.run_attempt_id, row.observation.derivation_id):
            continue
        yield row


def silver_fingerprints(store: Store, manifest: Manifest) -> set[Fingerprint]:
    """Every valid Silver version of the target's own lineage, as value fingerprints."""
    return {_fingerprint(row.observation) for row in _own_rows(store, manifest)}


def _group_fingerprints(store: Store, manifest: Manifest) -> tuple[set[Fingerprint], set[PairKey]]:
    """The dataset+transport group regardless of lineage (every sibling target included), for
    the sibling check: a version live attributes to this target and the rebuild to a sibling."""
    fingerprints: set[Fingerprint] = set()
    pairs: set[PairKey] = set()
    for row in store.iter_rows(
        manifest.contract.dataset_id, transport=manifest.contract.source_transport
    ):
        fingerprints.add(_fingerprint(row.observation))
        pairs.add(_pair(row.observation))
    return fingerprints, pairs


def _digest(fingerprints: set[Fingerprint]) -> SilverDigest:
    h = hashlib.sha256()
    for fp in sorted(fingerprints):
        h.update(fp)
    return SilverDigest(len(fingerprints), h.hexdigest())


def silver_digest(store: Store, manifest: Manifest) -> SilverDigest:
    return _digest(silver_fingerprints(store, manifest))


def _processed(store: Store, target_id: str) -> int:
    return Counter(r.state for r in store.runs(target_id))["processed"]


def _rebuild(
    rt: Runtime, scratch: Store, replica: Bronze, clock: Callable[[], datetime]
) -> tuple[int, tuple[ProcessReport, ...]]:
    """Rebuild the target in ``scratch`` from the replica: ``reconcile`` gives every run its
    newest capture and ``process`` maps it; then every run whose replica log holds **more than
    one payload change** is re-processed capture by capture, oldest first and the newest last,
    so the rebuild holds the version each capture produced, in the order live saw them (every
    occurrence, ADR-023 amendment 2), and the run ends on its newest capture — exactly as live
    does after a correction found changed content (ADR-033 §3). ``content_changed`` is not
    used: it is a flag against the target's newest entry, not against the run's previous capture
    (docs/07 §4.3); payload hashes are."""
    reconciled = reconcile(rt, window=None)
    reports = list(process(rt))
    derivation = derivation_for(rt.manifest, parser_ref(rt.manifest))
    by_run: dict[datetime, list[CaptureEntry]] = {}
    for entry in replica.log.list(rt.target_id):
        by_run.setdefault(entry.scheduled_for, []).append(entry)
    for scheduled_for, entries in by_run.items():
        # ADR-038: an invalidated capture is never replayed
        entries = [
            e for e in entries if not scratch.is_invalidated(e.capture_id, derivation.derivation_id)
        ]
        # every capture whose payload differs from the run's *previous* capture — consecutive,
        # not global: a payload that returns after another (A → B → A, ADR-023 amendment 2) is
        # replayed again so the rebuild records the same occurrences as live
        distinct: list[CaptureEntry] = []
        for entry in entries:  # ordered by attempt
            if not distinct or entry.payload_sha256 != distinct[-1].payload_sha256:
                distinct.append(entry)
        if len(distinct) < 2:
            continue
        run = scratch.get_run(rt.target_id, scheduled_for)
        if run is None:
            continue
        for entry in distinct:
            # claim and process this capture directly: ``process`` would first reconcile the
            # run back to its newest generation (ADR-024 amendment 1) and skip the older one
            scratch.mark_recaptured(run.id, entry.capture_id, now=clock())
            claim = scratch.claim(run.id, rt.owner, rt.lease_ttl, now=clock())
            if claim is None:
                continue
            reports.append(process_one(rt, claim, derivation))
    return len(reconciled), tuple(reports)


@dataclass(frozen=True, slots=True)
class _LiveSide:
    expected: set[Fingerprint]
    """The value of the newest derivation per (identity, payload) — what the rebuild must
    reproduce."""
    historical: set[Fingerprint]
    """Fingerprints of versions a newer derivation superseded for the same pair (a
    value-preserving revision shares the fingerprint with its successor)."""
    historical_versions: int
    historical_derivations: int
    processed: int
    lagging: int


def _within(snapshot: tuple[CaptureEntry, ...]) -> tuple[set[str], datetime | None]:
    return {e.capture_id for e in snapshot}, max((e.fetched_at for e in snapshot), default=None)


def _live_side(live: Store, manifest: Manifest, snapshot: tuple[CaptureEntry, ...]) -> _LiveSide:
    """What live holds that the replica must reproduce. ``bound`` is the replica's newest
    capture instant for the target. A live version or processed run whose capture is in the
    replica, or was fetched before ``bound``, is compared; one whose capture is newer than
    ``bound`` and not replicated yet is lag, not loss, and is counted as lagging instead. With
    no replica entry at all everything live holds is compared (and will be missing: the replica
    never received this target). Per pair, only the newest derivation's version is expected
    (ADR-036 amendment 5); the others are historical.

    Two streamed passes: the first collects the derivation ids (a handful), whose registration
    instants are then read **outside** any open cursor — on PostgreSQL every store read ends
    the transaction, which would destroy the named cursor of a pass in progress; the second
    pass decides the newest derivation per pair with those ranks in hand. ``snapshot`` is
    the replica's log as the rebuild saw it (``_Rebuilt.snapshot``)."""
    target = manifest.target_id
    replica_ids, bound = _within(snapshot)
    ids: set[str] = set()
    for row in _own_rows(live, manifest):
        if bound is None or row.observation.fetched_at <= bound:
            ids.add(row.observation.derivation_id)
    rank: dict[str, tuple[datetime, str]] = {}
    for derivation_id in ids:
        d = live.derivation(derivation_id)
        at = d.registered_at if d is not None and d.registered_at is not None else _EPOCH
        rank[derivation_id] = (at, derivation_id)
    newest: dict[PairKey, tuple[tuple[datetime, str], Fingerprint, str]] = {}
    historical: set[Fingerprint] = set()
    historical_versions = 0
    retired: set[str] = set()
    for row in _own_rows(live, manifest):
        o = row.observation
        if bound is not None and o.fetched_at > bound:
            continue
        key = _pair(o)
        candidate = (rank[o.derivation_id], _fingerprint(o), o.derivation_id)
        current = newest.get(key)
        if current is None:
            newest[key] = candidate
            continue
        loser = current if candidate[0] > current[0] else candidate
        if loser is current:
            newest[key] = candidate
        historical.add(loser[1])
        historical_versions += 1
        retired.add(loser[2])
    expected = {fp for _, fp, _ in newest.values()}
    # ADR-038: a run whose capture was invalidated is never rebuilt (reconcile skips the
    # capture, so a fresh scratch has no run for it), while live keeps the run it processed
    # before the decision — such a run is not expected from the rebuild (2026-09-25: 95 of
    # the demo's 368 processed XLSX runs, the 21-22 September invalidations, read as a shortfall)
    current_derivation = derivation_for(manifest, parser_ref(manifest)).derivation_id
    processed = 0
    lagging = 0
    for run in live.runs(target):
        if run.state != "processed":
            continue
        if run.capture_id is not None and live.is_invalidated(run.capture_id, current_derivation):
            continue
        if run.capture_id in replica_ids or bound is None:
            processed += 1
            continue
        # the capture is not in the replica: loss if it existed when the replica's newest
        # capture was fetched, lag otherwise. Its instant is the capture attempt that recorded
        # it (a reconciled run has none: the first processing start stands in)
        attempts = live.attempts(run.id)
        captured = [
            a.started_at for a in attempts if a.kind == "capture" and a.capture_id == run.capture_id
        ]
        starts = captured or [a.started_at for a in attempts if a.kind == "process"]
        if starts and min(starts) <= bound:
            processed += 1
        else:
            lagging += 1
    return _LiveSide(expected, historical, historical_versions, len(retired), processed, lagging)


@dataclass(frozen=True, slots=True)
class _Rebuilt:
    manifest: Manifest
    snapshot: tuple[CaptureEntry, ...]
    """The replica's capture log for the target as it was **before** the rebuild: the
    comparison uses this snapshot, never a fresh listing — replication runs on its own cadence,
    and a capture that lands in the replica between a target's rebuild and its comparison
    (minutes apart since every target is rebuilt first) would otherwise move the bound forward
    and read as loss (the demo's first scheduled drill under this rule, 2026-09-25 01:30 UTC:
    28 versions of one ceps_load capture replicated at 01:37, rebuilt at 01:31, compared at
    01:48)."""
    reconciled: int
    reports: tuple[ProcessReport, ...]
    failure: str | None = None

    @property
    def entries(self) -> int:
        return len(self.snapshot)


def _rebuild_target(
    manifest: Manifest,
    *,
    scratch: Store,
    replica: Bronze,
    clock: Callable[[], datetime],
    owner: str,
) -> _Rebuilt:
    snapshot = tuple(replica.log.list(manifest.target_id))
    rt = Runtime(
        manifest=manifest,
        bronze=replica,
        store=scratch,
        fetcher_factory=_never_fetch,
        clock=clock,
        owner=owner,
    )
    try:
        reconciled, reports = _rebuild(rt, scratch, replica, clock)
    except StoreUnavailable as exc:
        return _Rebuilt(manifest, snapshot, 0, (), f"store: {exc}")
    return _Rebuilt(manifest, snapshot, reconciled, reports)


def _dry_run_target(
    manifest: Manifest, *, live: Store | None, replica: Bronze
) -> TargetDrillReport:
    target = manifest.target_id
    entries = len(replica.log.list(target))
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


def _compare_target(rebuilt: _Rebuilt, *, live: Store | None, scratch: Store) -> TargetDrillReport:
    manifest = rebuilt.manifest
    target = manifest.target_id
    entries = rebuilt.entries
    if rebuilt.failure is not None:
        return TargetDrillReport(target, entries, 0, None, None, None, False, rebuilt.failure)
    reports = rebuilt.reports
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
            f"rebuilt {rebuilt.reconciled} runs, {len(reports)} processed, {len(failed)} failed "
            f"(no live store to compare)",
        )
    side = _live_side(live, manifest, rebuilt.snapshot)
    live_digest = _digest(side.expected)
    group_fp, group_pairs = _group_fingerprints(scratch, manifest)
    # a live pair absent from the whole rebuilt group is loss; a pair present with another value
    # is divergence (the fingerprint carries the value); a fingerprint present in the group but
    # not in this target's lineage was attributed to a sibling target — reproduced all the same
    unmatched = side.expected - scratch_fp
    sibling = {fp for fp in unmatched if fp in group_fp}
    unmatched -= sibling
    missing = 0
    diverging = 0
    for _, key in _expected_with_pairs(live, manifest, rebuilt.snapshot, unmatched):
        if key in group_pairs:
            diverging += 1
        else:
            missing += 1
    extra = len(scratch_fp - side.expected - side.historical)
    problems = []
    if failed:
        problems.append(f"{len(failed)} run(s) failed to process from the replica")
    if scratch_processed < side.processed:
        problems.append(f"processed runs {scratch_processed} < live {side.processed}")
    if missing:
        problems.append(f"{missing} Silver version(s) live holds are missing from the rebuild")
    if diverging:
        problems.append(
            f"{diverging} Silver version(s) live holds have another value under the running "
            f"implementation (an un-replayed correction, or a regression: replay --derivation, "
            f"or invalidate)"
        )
    if problems:
        message = "; ".join(problems)
    elif extra:
        message = (
            f"live ⊆ rebuild: {len(side.expected)} versions reproduced; the rebuild is ahead by "
            f"{extra} (live has captures it has not processed yet)"
        )
    else:
        message = f"identical: {len(side.expected)} Silver versions"
    if side.lagging:
        message += (
            f"; {side.lagging} live run(s) newer than the replica's last capture not compared"
        )
    if side.historical_versions:
        message += (
            f"; {side.historical_versions} version(s) under {side.historical_derivations} retired "
            f"derivation(s) not compared (the physical backup keeps them, ADR-036 amendment 5)"
        )
    if sibling:
        message += f"; {len(sibling)} version(s) reproduced under a sibling target"
    return TargetDrillReport(
        target,
        entries,
        scratch_processed,
        side.processed,
        scratch_digest,
        live_digest,
        not problems,
        message,
        missing_versions=missing,
        extra_versions=extra,
        lagging_runs=side.lagging,
        diverging_versions=diverging,
        historical_versions=side.historical_versions,
        historical_derivations=side.historical_derivations,
        sibling_versions=len(sibling),
    )


def _expected_with_pairs(
    live: Store,
    manifest: Manifest,
    snapshot: tuple[CaptureEntry, ...],
    unmatched: set[Fingerprint],
) -> Iterator[tuple[Fingerprint, PairKey]]:
    """The pair key of each unmatched expected fingerprint, by one more streamed pass over the
    target's own rows (only when something is unmatched; nothing is materialised)."""
    if not unmatched:
        return
    _, bound = _within(snapshot)
    seen: set[Fingerprint] = set()
    for row in _own_rows(live, manifest):
        o = row.observation
        if bound is not None and o.fetched_at > bound:
            continue
        fp = _fingerprint(o)
        if fp in unmatched and fp not in seen:
            seen.add(fp)
            yield fp, _pair(o)


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
    manifests = tuple(manifests)
    if dry_run:
        targets = tuple(_dry_run_target(m, live=live, replica=replica) for m in manifests)
    else:
        # every target is rebuilt before any is compared (review 3 R5): targets sharing a
        # dataset and transport must all be in the scratch store, whatever their order
        rebuilt = [
            _rebuild_target(m, scratch=scratch, replica=replica, clock=clock, owner=owner)
            for m in manifests
        ]
        targets = tuple(_compare_target(r, live=live, scratch=scratch) for r in rebuilt)
    finished = clock()
    return DrillReport(all(t.ok for t in targets), dry_run, started, finished, targets)
