"""ADR-002 restore drill on memory backends: rebuild from the replica equals live; a replica
missing a capture or a diverging value fails; dry run writes nothing."""

from __future__ import annotations

import itertools
from datetime import timedelta
from typing import cast

from energy_platform.bronze import Bronze, MemoryBlobStore, MemoryCaptureLog
from energy_platform.runtime import capture, process, restore_drill, silver_digest
from energy_platform.store import MemoryStore, Store, UnavailableStore
from tests.runtime.harness import DAY, SCHEDULED, T1, T3, Clock, runtime
from tests.synthetic import ote_im_price_period_response

_serial = itertools.count(1)


def distinct_t1_payload() -> bytes:
    """A T1 payload whose values differ per call, so every capture is its own Silver version
    (the default synthetic payload is identical across runs and would collapse versions)."""
    n = next(_serial)
    return ote_im_price_period_response(DAY).replace(b"170.13", f"{100 + n}.13".encode())


def live_system() -> tuple[MemoryStore, Bronze, Clock]:
    """Two targets, three runs each, processed: what production looks like before a drill."""
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    store = MemoryStore()
    bronze = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    for manifest in (T1, T3):
        payload = distinct_t1_payload if manifest is T1 else None
        rt = runtime(manifest, store=store, bronze=bronze, clock=clock, payload=payload)
        for k in range(3):
            when = SCHEDULED + timedelta(minutes=15 * k)
            clock.now = when + timedelta(minutes=1)
            assert capture(rt, when).outcome == "ok"
        process(rt)
    return store, bronze, clock


def test_rebuild_from_the_replica_matches_live() -> None:
    live, replica, clock = live_system()
    scratch = MemoryStore()
    report = restore_drill((T1, T3), scratch=scratch, replica=replica, live=live, clock=clock)
    assert report.ok, [t.message for t in report.targets]
    assert [t.target_id for t in report.targets] == ["ote_idm_soap", "ceps_load_soap"]
    for t in report.targets:
        assert t.replica_entries == 3 and t.scratch_processed == t.live_processed == 3
        assert t.scratch == t.live and t.scratch is not None and t.scratch.rows > 0
    assert silver_digest(scratch, T1) == silver_digest(live, T1)
    assert report.seconds >= 0 and not report.dry_run


def test_a_replica_missing_a_capture_fails_the_drill() -> None:
    live, replica, clock = live_system()
    partial = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    for entry in replica.log.list("ote_idm_soap")[:-1] + replica.log.list("ceps_load_soap"):
        partial.ingest(entry, replica.read(entry.raw_ref).payload)
    report = restore_drill((T1, T3), scratch=MemoryStore(), replica=partial, live=live, clock=clock)
    assert not report.ok
    t1, t3 = report.targets
    assert not t1.ok and "processed runs 2 < live 3" in t1.message
    assert t1.missing_versions > 0 and "missing from the rebuild" in t1.message
    assert t3.ok and t3.message.startswith("identical")


def test_a_diverging_value_in_live_is_detected_by_the_checksum() -> None:
    live, replica, clock = live_system()
    scratch = MemoryStore()
    baseline = restore_drill((T1,), scratch=scratch, replica=replica, live=live, clock=clock)
    assert baseline.ok
    # tamper with one live value: same row count, different checksum
    row = next(iter(live._rows.values()))
    tampered = row.observation.model_copy(update={"value": None})
    live._rows[row.id] = type(row)(row.id, row.run_attempt_id, tampered)
    again = restore_drill((T1,), scratch=MemoryStore(), replica=replica, live=live, clock=clock)
    assert not again.ok and again.targets[0].missing_versions == 1
    assert "missing from the rebuild" in again.targets[0].message


def test_dry_run_reports_and_writes_nothing() -> None:
    live, replica, clock = live_system()
    scratch = MemoryStore()
    report = restore_drill(
        (T1, T3), scratch=scratch, replica=replica, live=live, clock=clock, dry_run=True
    )
    assert report.ok and report.dry_run
    assert all(t.message.startswith("dry run: 3 replica entries") for t in report.targets)
    assert all(t.live_processed == 3 for t in report.targets)
    assert scratch.runs("ote_idm_soap") == () and scratch.runs("ceps_load_soap") == ()


def test_unreachable_scratch_store_fails_loudly() -> None:
    _, replica, clock = live_system()
    report = restore_drill((T1,), scratch=UnavailableStore(), replica=replica, clock=clock)
    assert not report.ok and "store:" in report.targets[0].message
    dry = restore_drill(
        (T1,),
        scratch=MemoryStore(),
        replica=replica,
        live=UnavailableStore(),
        clock=clock,
        dry_run=True,
    )
    assert not dry.ok  # live unreachable is reported in the dry run too


def test_without_a_live_store_the_rebuild_itself_is_the_check() -> None:
    _, replica, clock = live_system()
    report = restore_drill((T1, T3), scratch=MemoryStore(), replica=replica, clock=clock)
    assert report.ok and all(t.live is None and t.scratch is not None for t in report.targets)


def test_rebuild_ahead_of_live_is_not_a_failure() -> None:
    """Live has captured but not yet processed a run (its process CronJob has not fired): the
    rebuild processes everything and is ahead; nothing live holds is missing."""
    live, replica, clock = live_system()
    rt = runtime(T1, store=live, bronze=replica, clock=clock, payload=distinct_t1_payload)
    clock.now = SCHEDULED + timedelta(minutes=46)
    assert capture(rt, SCHEDULED + timedelta(minutes=45)).outcome == "ok"  # captured, unprocessed
    report = restore_drill((T1,), scratch=MemoryStore(), replica=replica, live=live, clock=clock)
    t1 = report.targets[0]
    assert report.ok and t1.ok and t1.extra_versions > 0 and t1.missing_versions == 0
    assert t1.scratch_processed == 4 and t1.live_processed == 3
    assert "ahead by" in t1.message


def test_the_drill_streams_rows_and_never_materialises_a_dataset() -> None:
    """2026-09-24: the first scheduled drill on the demo was OOM-killed at 512 MiB — it held
    every Silver version of a dataset as Python objects, three times over. The comparison now
    streams ``iter_rows`` and keeps one 16-byte fingerprint per version; ``all_rows`` must not
    be touched by the drill on either store."""
    live, replica, clock = live_system()
    scratch = MemoryStore()
    calls: list[str] = []

    class Spy:
        def __init__(self, inner: MemoryStore) -> None:
            self._inner = inner

        def all_rows(self, *args: object, **kwargs: object) -> object:
            calls.append("all_rows")
            raise AssertionError("the restore drill must stream rows, never materialise them")

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    report = restore_drill(
        (T1, T3),
        scratch=cast(Store, Spy(scratch)),
        replica=replica,
        live=cast(Store, Spy(live)),
        clock=clock,
    )
    assert report.ok and calls == []
    t1 = report.targets[0]
    assert t1.live is not None and t1.scratch is not None
    assert t1.live.checksum == t1.scratch.checksum and t1.live.rows == t1.scratch.rows > 0
    assert len(t1.live.checksum) == 64  # sha256 over the sorted fingerprints
