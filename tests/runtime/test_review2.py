"""Review 2 (2026-09-24) counterexamples as negative tests, through the runtime verbs.

Each test is the reviewer's probe (``codex-review/2026-09-24/evidence/data-correctness-probes
.py.txt``) with the assertion turned around: the probe asserted the defect, the test asserts the
fix. The store-level halves live in ``tests/store/test_store.py`` and run on PostgreSQL too.
"""

from __future__ import annotations

from datetime import timedelta

from energy_platform.runtime import capture, process
from energy_platform.store import MemoryStore
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
