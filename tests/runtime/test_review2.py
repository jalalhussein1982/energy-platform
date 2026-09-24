"""Review 2 (2026-09-24) counterexamples as negative tests, through the runtime verbs.

Each test is the reviewer's probe (``codex-review/2026-09-24/evidence/data-correctness-probes
.py.txt``) with the assertion turned around: the probe asserted the defect, the test asserts the
fix. The store-level halves live in ``tests/store/test_store.py`` and run on PostgreSQL too.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from energy_platform.contracts.manifest import Correction
from energy_platform.parse import parser_ref
from energy_platform.runtime import capture, process, process_one, reconcile, restore_drill
from energy_platform.store import (
    MemoryStore,
    Run,
    RunOrigin,
    RunState,
    Store,
    StoreUnavailable,
    derivation_for,
)
from tests.runtime.harness import DAY, SCHEDULED, T1, T2, Clock, runtime
from tests.synthetic import ote_im_price_period_response


def test_dc03_the_soap_owner_stays_canonical_when_the_xlsx_copy_arrives_later() -> None:
    """DC-03: T1 (SOAP) is the system of record for price_vwap and volume_total (01 §3 rule 2).
    The XLSX copy, fetched a minute later with another value, is stored, compared and
    reported — and never becomes the canonical row."""
    store = MemoryStore()
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    t1 = runtime(
        T1,
        payload=ote_im_price_period_response(DAY, [(1, "999.00", "1")]),
        store=store,
        clock=clock,
    )
    capture(t1, SCHEDULED)
    process(t1)
    clock.advance(timedelta(minutes=1))
    t2 = runtime(T2, store=store, clock=clock)
    capture(t2, SCHEDULED)
    process(t2)

    canonical = store.current_rows("ote.idm_continuous", metric="price_vwap")
    assert len(canonical) == 96  # SOAP delivered period 1 only; XLSX fills the other 95
    first = canonical[0]
    assert first.observation.period_index == 1
    assert first.observation.source_transport == "soap" and str(first.value) == "999.00"
    assert {r.observation.source_transport for r in canonical[1:]} == {"xlsx"}
    # the owner's row is never hidden behind a transport filter; the copy stays selectable
    soap = store.current_rows("ote.idm_continuous", metric="price_vwap", transport="soap")
    assert len(soap) == 1 and str(soap[0].value) == "999.00"
    copy = store.current_rows("ote.idm_continuous", metric="price_vwap", transport="xlsx")
    assert len(copy) == 96 and str(copy[0].value) == "170.13"
    # and the disagreement was seen: the copy's period 1 differs from the record's
    mismatches = store.quality_events("ote_idm_xlsx", kind="reconciliation_mismatch")
    assert mismatches and {e.metric for e in mismatches} == {"price_vwap", "volume_total"}


def test_dc04_a_provider_reversion_a_b_a_ends_at_a_and_the_rebuild_agrees() -> None:
    """DC-04 (ADR-023 amendment 2): the third capture returns the first payload; it is a new
    occurrence of that version, current again, and the drill's rebuild replays it too."""
    state = {"version": "A"}

    def payload() -> bytes:
        raw = ote_im_price_period_response(DAY)
        return raw if state["version"] == "A" else raw.replace(b"170.13", b"171.99")

    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, payload=payload, clock=clock)
    prices: list[str] = []
    outcomes: list[str] = []
    for index, version in enumerate(("A", "B", "A")):
        state["version"] = version
        cap = capture(rt, SCHEDULED, force=index > 0)
        assert cap.entry is not None and cap.entry.content_changed
        reports = process(rt)
        outcomes.append(reports[0].outcome)
        prices.append(
            str(rt.store.current_rows("ote.idm_continuous", metric="price_vwap")[0].value)
        )
        clock.advance(timedelta(minutes=1))
    assert prices == ["170.13", "171.99", "170.13"]
    assert outcomes == ["ok", "ok", "ok"]  # the third added occurrences, not versions
    assert len(rt.store.all_rows("ote.idm_continuous")) == 2 * 2 * 96  # two versions per row

    scratch = MemoryStore()
    report = restore_drill((T1,), scratch=scratch, replica=rt.bronze, live=rt.store, clock=clock)
    assert report.ok and report.targets[0].missing_versions == 0
    assert str(scratch.current_rows("ote.idm_continuous", metric="price_vwap")[0].value) == "170.13"


class _ToggleStore(MemoryStore):
    """A ledger that can be taken down between Bronze and the acknowledgment."""

    down = False

    def ensure_run(
        self,
        target_id: str,
        scheduled_for: datetime,
        *,
        state: RunState,
        origin: RunOrigin,
        capture_id: str | None = None,
        now: datetime,
    ) -> Run:
        if self.down:
            raise StoreUnavailable("injected post-Bronze outage")
        return super().ensure_run(
            target_id, scheduled_for, state=state, origin=origin, capture_id=capture_id, now=now
        )


def _corrigible(price_after: bytes = b"171.99") -> tuple[dict[str, bool], Callable[[], bytes]]:
    state = {"corrected": False}

    def payload() -> bytes:
        raw = ote_im_price_period_response(DAY)
        return raw.replace(b"170.13", price_after) if state["corrected"] else raw

    return state, payload


def _price(store: Store) -> str:
    return str(store.current_rows("ote.idm_continuous", metric="price_vwap")[0].value)


def test_dc01_a_correction_captured_during_a_ledger_outage_is_reconciled_and_processed() -> None:
    """DC-01 (ADR-024 amendment 1): Bronze holds the correction, the ledger missed the
    acknowledgment; the next reconcile advances the run to the newer generation."""
    state, payload = _corrigible()
    store = _ToggleStore()
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, payload=payload, store=store, clock=clock)
    capture(rt, SCHEDULED)
    process(rt)
    state["corrected"] = True
    clock.advance(timedelta(hours=1))
    store.down = True
    new = capture(rt, SCHEDULED, force=True)
    store.down = False
    assert new.entry is not None and new.entry.content_changed and not new.ledger_updated

    recovered = reconcile(rt)
    assert [r.capture_id for r in recovered] == [new.entry.capture_id]
    reports = process(rt)
    assert [r.outcome for r in reports] == ["ok"] and _price(store) == "171.99"
    run = store.get_run(T1.target_id, SCHEDULED)
    assert run is not None and run.state == "processed" and run.capture_id == new.entry.capture_id


def test_dc01_a_subsequent_unchanged_poll_does_not_hide_the_missed_correction() -> None:
    """The poll after the outage sees the same bytes as the correction (unchanged against its
    baseline, so it marks nothing); reconcile still compares the run's payload with the newest."""
    state, payload = _corrigible()
    store = _ToggleStore()
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, payload=payload, store=store, clock=clock)
    capture(rt, SCHEDULED)
    process(rt)
    state["corrected"] = True
    clock.advance(timedelta(hours=1))
    store.down = True
    capture(rt, SCHEDULED, force=True)
    store.down = False
    clock.advance(timedelta(hours=1))
    poll = capture(rt, SCHEDULED, force=True)
    assert poll.entry is not None and not poll.entry.content_changed and poll.ledger_updated
    assert process(rt)  # reconcile inside process advanced the run
    assert _price(store) == "171.99"


def test_dc01_a_correction_of_an_older_day_is_inside_the_reconcile_window() -> None:
    """The reconcile window is the lookback plus the manifest's correction days, so a D-3
    re-poll captured during an outage is found by the default 48-hour reconcile."""
    state, payload = _corrigible()
    store = _ToggleStore()
    old_run = SCHEDULED - timedelta(days=3)
    clock = Clock(old_run + timedelta(minutes=1))
    correction = Correction(cron="7 3 * * *", days=3)  # the committed T1 manifest's window
    manifest = T1.model_copy(
        update={"cadence": T1.cadence.model_copy(update={"correction": correction})}
    )
    rt = runtime(manifest, payload=payload, store=store, clock=clock)
    capture(rt, old_run)
    process(rt)
    state["corrected"] = True
    clock.now = SCHEDULED + timedelta(minutes=1)  # three days later
    store.down = True
    capture(rt, old_run, force=True)
    store.down = False
    assert reconcile(rt, window=rt.reconcile_window)  # found although scheduled_for is D-3
    assert process(rt) and _price(store) == "171.99"


def test_dc02_a_recapture_during_an_in_flight_claim_fences_the_old_worker() -> None:
    """DC-02 (ADR-024 amendment 1): the slow worker's commit for A loses its lease; B is
    processed by the next worker and is what the current view shows."""
    state, payload = _corrigible()
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, payload=payload, clock=clock)
    capture(rt, SCHEDULED)
    run = rt.store.get_run(T1.target_id, SCHEDULED)
    assert run is not None
    old_claim = rt.store.claim(run.id, "slow-worker", rt.lease_ttl, now=clock())
    assert old_claim is not None
    state["corrected"] = True
    clock.advance(timedelta(minutes=1))
    correction = capture(rt, SCHEDULED, force=True)
    assert correction.entry is not None and correction.entry.content_changed

    old = process_one(rt, old_claim, derivation_for(T1, parser_ref(T1)))
    assert old.outcome == "lost_lease" and old.inserted == 0
    run = rt.store.get_run(T1.target_id, SCHEDULED)
    assert run is not None and run.state == "captured" and run.fence == old_claim.fence + 1
    assert run.capture_id == correction.entry.capture_id
    later = process(rt)
    assert [r.outcome for r in later] == ["ok"] and _price(rt.store) == "171.99"
