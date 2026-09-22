"""ADR-002 restore drill on memory backends: rebuild from the replica equals live; a replica
missing a capture or a diverging value fails; dry run writes nothing."""

from __future__ import annotations

from datetime import timedelta

from energy_platform.bronze import Bronze, MemoryBlobStore, MemoryCaptureLog
from energy_platform.runtime import capture, process, restore_drill, silver_digest
from energy_platform.store import MemoryStore, UnavailableStore
from tests.runtime.harness import SCHEDULED, T1, T3, Clock, runtime


def live_system() -> tuple[MemoryStore, Bronze, Clock]:
    """Two targets, three runs each, processed: what production looks like before a drill."""
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    store = MemoryStore()
    bronze = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    for manifest in (T1, T3):
        rt = runtime(manifest, store=store, bronze=bronze, clock=clock)
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
    assert not t1.ok and "processed runs 2 != live 3" in t1.message
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
    assert not again.ok and "checksum differs" in again.targets[0].message


def test_dry_run_reports_and_writes_nothing() -> None:
    live, replica, clock = live_system()
    scratch = MemoryStore()
    report = restore_drill(
        (T1, T3), scratch=scratch, replica=replica, live=live, clock=clock, dry_run=True
    )
    assert report.ok and report.dry_run
    assert all(t.message == "dry run: 3 replica entries" for t in report.targets)
    assert scratch.runs("ote_idm_soap") == () and scratch.runs("ceps_load_soap") == ()


def test_unreachable_scratch_store_fails_loudly() -> None:
    _, replica, clock = live_system()
    report = restore_drill((T1,), scratch=UnavailableStore(), replica=replica, clock=clock)
    assert not report.ok and "store:" in report.targets[0].message
    dry = restore_drill(
        (T1,), scratch=UnavailableStore(), replica=replica, clock=clock, dry_run=True
    )
    assert not dry.ok


def test_without_a_live_store_the_rebuild_itself_is_the_check() -> None:
    _, replica, clock = live_system()
    report = restore_drill((T1, T3), scratch=MemoryStore(), replica=replica, clock=clock)
    assert report.ok and all(t.live is None and t.scratch is not None for t in report.targets)
