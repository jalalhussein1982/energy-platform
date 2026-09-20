"""ADR-024 §6 crash matrix, one test per row, memory backends, plus the happy path."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from energy_platform.bronze import Bronze, CaptureEntry, MemoryBlobStore, MemoryCaptureLog
from energy_platform.parse import parser_ref
from energy_platform.runtime import (
    backfill,
    capture,
    detect_gaps,
    process,
    process_one,
    reconcile,
    replay_derivation,
    replay_range,
)
from energy_platform.store import MemoryStore, StoreUnavailable, derivation_for
from tests.runtime.harness import DAY, SCHEDULED, T1, T2, T3, Clock, runtime
from tests.synthetic import ote_im_price_period_response, soap_fault


def test_happy_path_capture_then_process_writes_silver_and_completeness() -> None:
    rt = runtime(T1)
    report = capture(rt, SCHEDULED)
    assert report.outcome == "ok" and report.created and report.ledger_updated
    assert report.entry is not None and report.entry.attempt == 1
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "captured" and run.capture_id == report.entry.capture_id
    assert [a.kind for a in rt.store.attempts(run.id)] == ["capture"]

    reports = process(rt)
    assert len(reports) == 1
    assert reports[0].outcome == "ok" and reports[0].inserted == 2 * 96
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "processed" and run.lease_owner is None
    current = rt.store.current_rows("ote.idm_continuous", metric="price_vwap")
    assert len(current) == 96 and current[0].value == Decimal("170.13")
    kinds = [e.kind for e in rt.store.quality_events("ote_idm_soap")]
    assert kinds == ["partition_status"]
    assert rt.store.quality_events("ote_idm_soap")[0].message == "2026-09-18: complete 96/96"
    d = derivation_for(T1, parser_ref(T1))
    assert rt.store.derivation(d.derivation_id) is not None


def test_row_1_crash_after_blob_put_before_entry_put() -> None:
    class DeadLog(MemoryCaptureLog):
        def put(self, entry: CaptureEntry) -> None:
            raise OSError("object store died mid-write")

    blobs = MemoryBlobStore()
    dead = runtime(T1, bronze=Bronze(blobs, DeadLog()))
    try:
        capture(dead, SCHEDULED)
    except OSError:
        pass  # the worker died; the orphan blob is content-addressed and harmless
    assert len(blobs) == 1
    healthy = runtime(T1, bronze=Bronze(blobs, MemoryCaptureLog()), store=dead.store)
    report = capture(healthy, SCHEDULED)  # next run re-captures the same instant
    assert report.outcome == "ok" and report.created and len(blobs) == 1


def test_row_2_crash_after_entry_put_before_ledger_row_is_reconciled() -> None:
    class LedgerDown(MemoryStore):
        def ensure_run(self, *a: Any, **kw: Any) -> Any:
            raise StoreUnavailable("postgres unreachable")

    down = runtime(T1, store=LedgerDown())
    report = capture(down, SCHEDULED)
    assert report.outcome == "ok" and report.created and report.ledger_updated is False
    assert len(down.bronze.log.list("ote_idm_soap")) == 1  # capture is complete
    store = MemoryStore()
    later = runtime(T1, bronze=down.bronze, store=store)
    touched = reconcile(later)
    assert (
        len(touched) == 1 and touched[0].origin == "reconciled" and touched[0].state == "captured"
    )
    assert process(later)[0].outcome == "ok"


def test_row_3_store_down_during_capture_then_process_picks_it_up() -> None:
    class Down(MemoryStore):
        def ensure_run(self, *a: Any, **kw: Any) -> Any:
            raise StoreUnavailable("down")

        def record_attempt(self, *a: Any, **kw: Any) -> Any:
            raise StoreUnavailable("down")

    rt = runtime(T1, store=Down())
    assert capture(rt, SCHEDULED).ledger_updated is False
    recovered = runtime(T1, bronze=rt.bronze, store=MemoryStore())
    reports = process(recovered)  # process starts with reconcile (ADR-024 §2)
    assert [r.outcome for r in reports] == ["ok"]
    run = recovered.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.origin == "reconciled" and run.state == "processed"


def test_row_4_two_workers_claim_one_run_second_claim_fails() -> None:
    store = MemoryStore()
    bronze = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    w1 = runtime(T1, store=store, bronze=bronze, owner="w1")
    w2 = runtime(T1, store=store, bronze=bronze, owner="w2")
    capture(w1, SCHEDULED)
    run = store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None
    first = store.claim(run.id, "w1", w1.lease_ttl, now=w1.clock())
    assert first is not None
    assert process(w2) == ()  # w2 sees the run but cannot claim it
    d = derivation_for(T1, parser_ref(T1))
    assert process_one(w1, first, d).outcome == "ok"


def test_row_5_lease_expires_and_the_old_holder_commits_late_with_zero_rows() -> None:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    store = MemoryStore()
    bronze = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    w1 = runtime(T1, store=store, bronze=bronze, clock=clock, owner="w1")
    w2 = runtime(T1, store=store, bronze=bronze, clock=clock, owner="w2")
    capture(w1, SCHEDULED)
    run = store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None
    d = derivation_for(T1, parser_ref(T1))
    old = store.claim(run.id, "w1", w1.lease_ttl, now=clock())
    assert old is not None
    clock.advance(w1.lease_ttl + timedelta(seconds=1))  # w1 stalls; its lease expires
    new_reports = process(w2)
    assert new_reports[0].outcome == "ok" and new_reports[0].inserted == 192
    stale = process_one(w1, old, d)  # w1 wakes up and tries to commit
    assert stale.outcome == "lost_lease" and stale.inserted == 0
    assert len(store.all_rows("ote.idm_continuous")) == 192
    assert [a.outcome for a in store.attempts(run.id) if a.kind == "process"] == [
        "lost_lease",
        "ok",
    ]


def test_row_6_never_captured_inside_max_age_is_backfilled() -> None:
    clock = Clock(SCHEDULED + timedelta(hours=1))
    rt = runtime(T1, clock=clock)
    gaps = detect_gaps(rt, lookback=timedelta(hours=2))  # instants 21:30 .. 23:15 UTC
    missing = [g for g in gaps if g.kind == "missing_capture"]
    assert SCHEDULED in {g.scheduled_for for g in missing}
    assert all(clock.now - g.scheduled_for >= timedelta(minutes=30) for g in missing)
    assert all(
        g.kind == "pending" for g in gaps if clock.now - g.scheduled_for < timedelta(minutes=30)
    )
    runs = rt.store.runs("ote_idm_soap")
    assert len(runs) == len(missing) == 6
    assert all(r.state == "missing_capture" and r.origin == "backfill" for r in runs)
    reports = backfill(rt)
    assert len(reports) == 6 and all(r.outcome == "ok" and r.created for r in reports)
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "captured"
    assert [a.kind for a in rt.store.attempts(run.id)] == ["backfill"]
    assert len(process(rt)) == 6
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "processed"
    assert {g.kind for g in detect_gaps(rt, lookback=timedelta(hours=2))} == {"pending"}


def test_row_7_never_captured_outside_max_age_is_unrecoverable_and_alerted() -> None:
    data = T1.model_dump(mode="json")
    data["history"]["max_age"] = "PT30M"
    from energy_platform.contracts.manifest import Manifest

    short = Manifest.model_validate(data)
    clock = Clock(SCHEDULED + timedelta(hours=2))
    rt = runtime(short, clock=clock)
    gaps = detect_gaps(rt, lookback=timedelta(hours=2))
    kinds = {g.kind for g in gaps}
    assert "unrecoverable" in kinds
    old = [g for g in gaps if g.kind == "unrecoverable"]
    assert all(clock.now - g.scheduled_for > timedelta(minutes=30) for g in old)
    alerts = rt.store.quality_events("ote_idm_soap", kind="unrecoverable_gap")
    assert len(alerts) == len(old) and all(a.severity == "error" for a in alerts)
    fetched = backfill(rt)  # only the still-recoverable instants are fetched
    assert fetched and all(clock.now - r.scheduled_for <= timedelta(minutes=30) for r in fetched)
    assert {r.scheduled_for for r in fetched}.isdisjoint({g.scheduled_for for g in old})
    detect_gaps(rt, lookback=timedelta(hours=2))  # a second pass does not alert again
    assert len(rt.store.quality_events("ote_idm_soap", kind="unrecoverable_gap")) == len(old)


def test_row_8_replay_of_a_capture_already_processed_by_the_same_derivation_is_a_noop() -> None:
    rt = runtime(T1)
    capture(rt, SCHEDULED)
    assert process(rt)[0].inserted == 192
    queued = replay_range(rt, SCHEDULED - timedelta(minutes=1), SCHEDULED + timedelta(minutes=1))
    assert len(queued) == 1 and queued[0].kind == "replay"
    reports = process(rt)
    assert len(reports) == 1
    assert reports[0].attempt_kind == "replay" and reports[0].outcome == "noop"
    assert reports[0].inserted == 0
    assert len(rt.store.all_rows("ote.idm_continuous")) == 192
    assert replay_range(rt, SCHEDULED + timedelta(hours=1), SCHEDULED + timedelta(hours=2)) == ()


def test_replay_by_derivation_targets_the_captures_that_carry_it() -> None:
    rt = runtime(T1)
    capture(rt, SCHEDULED)
    process(rt)
    d = derivation_for(T1, parser_ref(T1))
    assert len(replay_derivation(rt, d.derivation_id)) == 1
    assert replay_derivation(rt, "0000000000000000") == ()
    assert replay_derivation(rt, d.derivation_id) == ()  # already pending


def test_quarantined_document_commits_no_rows_and_keeps_bronze() -> None:
    rt = runtime(T1, payload=soap_fault())
    capture(rt, SCHEDULED)
    reports = process(rt)
    assert reports[0].outcome == "quarantined" and "SOAP Fault" in (reports[0].error or "")
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "failed"
    assert rt.store.all_rows("ote.idm_continuous") == ()
    events = rt.store.quality_events("ote_idm_soap")
    assert [e.kind for e in events] == ["quarantine"]
    assert len(rt.bronze.log.list("ote_idm_soap")) == 1  # payload kept for replay after a fix


def test_source_unavailable_writes_nothing_to_bronze_but_records_the_attempt() -> None:
    from energy_platform.fetch import Fetcher, FixtureTransport

    def failing(manifest: Any) -> Fetcher:
        return Fetcher(
            allowed_hosts=manifest.allowed_hosts,
            transport=FixtureTransport(b"down", status=503),
            offline=True,
            sleep=lambda s: None,
        )

    rt = replace(runtime(T1), fetcher_factory=failing)
    report = capture(rt, SCHEDULED)
    assert report.outcome == "source_unavailable" and report.entry is None
    assert rt.bronze.log.list("ote_idm_soap") == ()
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "scheduled"
    assert [a.outcome for a in rt.store.attempts(run.id)] == ["source_unavailable"]


def test_capture_is_idempotent_per_instant() -> None:
    rt = runtime(T1)
    first = capture(rt, SCHEDULED)
    second = capture(rt, SCHEDULED)
    assert first.created and not second.created and second.outcome == "noop"
    assert second.entry == first.entry


def test_t2_and_t3_run_end_to_end_with_reconciliation_across_transports() -> None:
    store = MemoryStore()
    t1 = runtime(T1, store=store)
    capture(t1, SCHEDULED)
    assert process(t1)[0].inserted == 192
    t2 = runtime(T2, store=store)
    capture(t2, SCHEDULED)
    r2 = process(t2)[0]
    assert r2.inserted == 7 * 96
    # synthetic T1 and T2 share price_vwap generation (170 + i*0.13) and volume (120 + i*0.275)
    assert store.quality_events("ote_idm_xlsx", kind="reconciliation_mismatch") == ()
    assert [e.kind for e in store.quality_events("ote_idm_xlsx")] == [
        "unknown_field",
        "partition_status",
    ]
    t3 = runtime(T3, store=store)
    capture(t3, SCHEDULED)
    assert process(t3)[0].inserted == 2 * 96
    assert len(store.current_rows("ceps.load")) == 192


def test_t2_copy_that_disagrees_with_t1_raises_a_mismatch() -> None:
    store = MemoryStore()
    t1 = runtime(T1, store=store, payload=ote_im_price_period_response(DAY, [(1, "999.00", "1")]))
    capture(t1, SCHEDULED)
    process(t1)
    t2 = runtime(T2, store=store)
    capture(t2, SCHEDULED)
    process(t2)
    events = store.quality_events("ote_idm_xlsx", kind="reconciliation_mismatch")
    assert {e.metric for e in events} == {"price_vwap", "volume_total"}  # period 1 only
    assert len(events) == 2
    assert any("soap=999.00 vs copy=170.13" in e.message for e in events)


def test_process_reports_pending_run_held_elsewhere_is_skipped(monkeypatch: Any) -> None:
    rt = runtime(T1)
    capture(rt, SCHEDULED)
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None
    rt.store.claim(run.id, "other", timedelta(hours=1), now=rt.clock())
    assert process(rt) == ()


def test_datetime_of_delivery_day_is_the_prague_date(monkeypatch: Any) -> None:
    from energy_platform.runtime import delivery_day_for

    assert delivery_day_for(datetime.fromisoformat("2026-09-17T22:15:00+00:00")) == DAY
