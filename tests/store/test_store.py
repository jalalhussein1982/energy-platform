"""The six ADR-023 proofs, fencing (ADR-024 §4) and the ledger, on memory and on Postgres.

Every test takes the ``store`` fixture and therefore runs twice: on ``MemoryStore`` always and
on ``PostgresStore`` when ``make db-test`` provides a server.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from energy_platform.mapping.quality import QualityEvent
from energy_platform.store import Claim, Store
from tests.store.rows import D_A, D_B, FETCH_1, FETCH_2, SHA_1, SHA_2, T0, obs

NOW = datetime(2026, 9, 18, 0, 10, tzinfo=UTC)
TTL = timedelta(minutes=5)


def captured_run(store: Store, target: str = "ote_idm_soap", when: datetime = T0) -> int:
    run = store.ensure_run(
        target, when, state="captured", origin="scheduled", capture_id="c1", now=NOW
    )
    return run.id


def claim(store: Store, run_id: int, owner: str = "w1", now: datetime = NOW) -> Claim:
    c = store.claim(run_id, owner, TTL, now=now)
    assert c is not None
    return c


def values(store: Store, metric: str = "price_vwap") -> dict[int | None, Decimal | None]:
    return {
        r.observation.period_index: r.value
        for r in store.current_rows("ote.idm_continuous", metric=metric)
    }


# ------------------------------------------------------------------ ADR-023 proofs


def test_proof_1_exact_retry_inserts_nothing(store: Store) -> None:
    run = captured_run(store)
    first = store.commit(
        claim(store, run),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs()],
        now=NOW,
    )
    assert first.inserted == 1
    again = store.commit(
        claim(store, run, now=NOW + TTL),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs()],
        now=NOW + TTL,
    )
    assert again.inserted == 0 and again.lost_lease is False
    assert len(store.all_rows("ote.idm_continuous")) == 1


def test_proof_2_same_payload_new_derivation_appends_and_becomes_current(store: Store) -> None:
    run = captured_run(store)
    store.commit(
        claim(store, run),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs(value="170.13")],
        now=NOW,
    )
    later = NOW + TTL
    fixed = obs(value="-170.13", derivation=D_B)  # a sign fix in the implementation
    store.commit(
        claim(store, run, now=later),
        state="processed",
        outcome="ok",
        derivation=D_B,
        observations=[fixed],
        now=later,
    )
    assert len(store.all_rows("ote.idm_continuous")) == 2  # old row stays
    current = store.current_rows("ote.idm_continuous")
    assert len(current) == 1 and current[0].value == Decimal("-170.13")
    assert current[0].observation.derivation_id == D_B.derivation_id
    assert current[0].ordering_basis == "fetched_at"


def test_proof_3_older_capture_replayed_later_does_not_outrank_a_newer_capture(
    store: Store,
) -> None:
    run1 = captured_run(store, when=T0)
    run2 = store.ensure_run(
        "ote_idm_soap",
        T0 + timedelta(minutes=15),
        state="captured",
        origin="scheduled",
        capture_id="c2",
        now=NOW,
    ).id
    # capture 1 (fetched 00:05) and capture 2 (fetched 00:20) both describe period 1
    store.commit(
        claim(store, run1),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs(value="1", sha=SHA_1, fetched_at=FETCH_1)],
        now=NOW,
    )
    store.commit(
        claim(store, run2),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs(value="2", sha=SHA_2, fetched_at=FETCH_2)],
        now=NOW,
    )
    assert values(store)[1] == Decimal("2")
    # replay capture 1 much later with a newer derivation: ordering basis is the capture's
    replay_time = NOW + timedelta(days=1)
    store.commit(
        claim(store, run1, now=replay_time),
        state="processed",
        outcome="ok",
        derivation=D_B,
        observations=[obs(value="1", sha=SHA_1, fetched_at=FETCH_1, derivation=D_B)],
        now=replay_time,
    )
    assert values(store)[1] == Decimal("2")
    assert len(store.all_rows("ote.idm_continuous")) == 3


def test_proof_4_t1_t2_ownership_holds_across_retry_and_new_derivation(store: Store) -> None:
    t1 = captured_run(store, "ote_idm_soap")
    t2 = captured_run(store, "ote_idm_xlsx")
    soap = [obs("price_vwap", "170.13"), obs("volume_total", "125.275")]
    xlsx = [
        obs("price_vwap", "170.13", transport="xlsx", sha=SHA_2),
        obs("price_min", "165.00", transport="xlsx", sha=SHA_2),
    ]
    store.commit(
        claim(store, t1),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=soap,
        now=NOW,
    )
    store.commit(
        claim(store, t2),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=xlsx,
        now=NOW,
    )
    # both copies of price_vwap are stored: rows are metric-long, identity has no transport
    assert len(store.all_rows("ote.idm_continuous")) == 4
    by_transport = {
        r.observation.source_transport
        for r in store.current_rows("ote.idm_continuous", metric="price_vwap")
    }
    assert (
        by_transport
    )  # a current row exists; which copy wins is decided by fetched_at, not by transport
    assert store.current_rows("ote.idm_continuous", metric="price_vwap", transport="soap")
    assert store.current_rows("ote.idm_continuous", metric="price_min", transport="soap") == ()
    # exact retry of both and a re-derivation of T1 leave T2-only metrics untouched
    store.commit(
        claim(store, t2, now=NOW + TTL),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=xlsx,
        now=NOW + TTL,
    )
    store.commit(
        claim(store, t1, now=NOW + TTL),
        state="processed",
        outcome="ok",
        derivation=D_B,
        observations=[o.model_copy(update={"derivation_id": D_B.derivation_id}) for o in soap],
        now=NOW + TTL,
    )
    assert len(store.all_rows("ote.idm_continuous")) == 6
    assert values(store, "price_min")[1] == Decimal("165.00")


def test_proof_5_null_source_version_retry_is_a_no_op(store: Store) -> None:
    run = captured_run(store)
    row = obs(source_version=None)
    store.commit(
        claim(store, run),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[row],
        now=NOW,
    )
    again = store.commit(
        claim(store, run, now=NOW + TTL),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[row],
        now=NOW + TTL,
    )
    assert again.inserted == 0
    assert len(store.all_rows("ote.idm_continuous")) == 1
    # a *versioned* twin is a different identity
    versioned = obs(
        source_version="1",
        dataset_id="ceps.load",
        metric="load",
        dimensions={"area": "CZ", "aggregation_function": "AVG"},
    )
    ceps = captured_run(store, "ceps_load_soap")
    assert (
        store.commit(
            claim(store, ceps),
            state="processed",
            outcome="ok",
            derivation=D_A,
            observations=[versioned],
            now=NOW,
        ).inserted
        == 1
    )


def test_proof_6_provider_correction_appends_regardless_of_derivation(store: Store) -> None:
    run1 = captured_run(store, when=T0)
    run2 = store.ensure_run(
        "ote_idm_soap",
        T0 + timedelta(minutes=15),
        state="captured",
        origin="scheduled",
        capture_id="c2",
        now=NOW,
    ).id
    store.commit(
        claim(store, run1),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs(value="170.13", sha=SHA_1, fetched_at=FETCH_1)],
        now=NOW,
    )
    store.commit(
        claim(store, run2),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs(value="170.99", sha=SHA_2, fetched_at=FETCH_2)],
        now=NOW,
    )
    assert len(store.all_rows("ote.idm_continuous")) == 2
    assert values(store)[1] == Decimal("170.99")


def test_source_published_at_outranks_fetched_at_when_present(store: Store) -> None:
    run = captured_run(store)
    early_pub = obs(
        value="1", sha=SHA_1, fetched_at=FETCH_2, published=FETCH_1 - timedelta(hours=1)
    )
    late_pub = obs(value="2", sha=SHA_2, fetched_at=FETCH_1, published=FETCH_1)
    store.commit(
        claim(store, run),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[early_pub, late_pub],
        now=NOW,
    )
    current = store.current_rows("ote.idm_continuous")
    assert current[0].value == Decimal("2") and current[0].ordering_basis == "source_published_at"


# ------------------------------------------------------------------ ADR-024 §4 fencing


def test_second_claim_fails_while_the_lease_is_live(store: Store) -> None:
    run = captured_run(store)
    first = store.claim(run, "w1", TTL, now=NOW)
    assert first is not None and first.fence == 1
    assert store.claim(run, "w2", TTL, now=NOW + timedelta(minutes=1)) is None


def test_expired_lease_is_reclaimed_and_the_stale_holder_commits_nothing(store: Store) -> None:
    run = captured_run(store)
    old = claim(store, run, "w1", now=NOW)
    new = claim(store, run, "w2", now=NOW + TTL + timedelta(seconds=1))
    assert (old.fence, new.fence) == (1, 2)
    stale = store.commit(
        old,
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs()],
        now=NOW + TTL + timedelta(minutes=1),
    )
    assert stale.lost_lease is True and stale.inserted == 0
    assert store.all_rows("ote.idm_continuous") == ()
    assert store.get_run("ote_idm_soap", T0) is not None
    assert next(a for a in store.attempts(run) if a.id == old.attempt.id).outcome == "lost_lease"
    live = store.commit(
        new,
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs()],
        now=NOW + TTL + timedelta(minutes=2),
    )
    assert live.inserted == 1
    final = store.get_run("ote_idm_soap", T0)
    assert final is not None and final.state == "processed" and final.lease_owner is None


def test_renew_extends_only_the_current_holder(store: Store) -> None:
    run = captured_run(store)
    old = claim(store, run, "w1", now=NOW)
    assert store.renew(old, TTL, now=NOW + timedelta(minutes=1)) is True
    new = claim(store, run, "w2", now=NOW + timedelta(minutes=1) + TTL + timedelta(seconds=1))
    assert store.renew(old, TTL, now=NOW + timedelta(minutes=10)) is False
    assert store.renew(new, TTL, now=NOW + timedelta(minutes=10)) is True


def test_events_and_quarantine_outcome_are_recorded_under_the_fence(store: Store) -> None:
    run = captured_run(store)
    c = claim(store, run)
    result = store.commit(
        c,
        state="failed",
        outcome="quarantined",
        error="changed header",
        events=[QualityEvent("quarantine", "error", "changed header", "IM!row6")],
        now=NOW,
    )
    assert result.inserted == 0
    events = store.quality_events("ote_idm_soap")
    assert (
        len(events) == 1
        and events[0].kind == "quarantine"
        and events[0].run_attempt_id == c.attempt.id
    )
    r = store.get_run("ote_idm_soap", T0)
    assert r is not None and r.state == "failed"


# ------------------------------------------------------------------ ledger bookkeeping


def test_ensure_run_is_idempotent_and_records_the_capture_once(store: Store) -> None:
    a = store.ensure_run("t", T0, state="scheduled", origin="scheduled", now=NOW)
    b = store.ensure_run("t", T0, state="captured", origin="reconciled", capture_id="c1", now=NOW)
    c = store.ensure_run("t", T0, state="captured", origin="reconciled", capture_id="c9", now=NOW)
    assert a.id == b.id == c.id
    assert (b.state, b.capture_id, b.origin) == ("captured", "c1", "scheduled")
    assert c.capture_id == "c1"  # a second capture id never overwrites the first
    store.commit(claim(store, a.id), state="processed", outcome="ok", now=NOW)
    d = store.ensure_run("t", T0, state="captured", origin="reconciled", capture_id="c1", now=NOW)
    assert d.state == "processed"  # never lowered


def test_pending_runs_and_replay_queue(store: Store) -> None:
    run = captured_run(store)
    assert [r.id for r in store.pending_runs("ote_idm_soap")] == [run]
    store.commit(
        claim(store, run),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs()],
        now=NOW,
    )
    assert store.pending_runs("ote_idm_soap") == ()
    queued = store.enqueue_replay(run, now=NOW)
    assert queued is not None and queued.kind == "replay" and queued.pending
    assert store.enqueue_replay(run, now=NOW) is None  # one pending replay at a time
    assert [r.id for r in store.pending_runs("ote_idm_soap")] == [run]
    c = claim(store, run, now=NOW + TTL)
    assert c.attempt.id == queued.id and c.attempt.kind == "replay" and c.attempt.capture_id == "c1"
    store.commit(
        c, state="processed", outcome="noop", derivation=D_A, observations=[obs()], now=NOW + TTL
    )
    assert store.pending_runs("ote_idm_soap") == ()
    kinds = [a.kind for a in store.attempts(run)]
    assert kinds == ["process", "replay"]


def test_runs_with_derivation_finds_the_captures_to_repair(store: Store) -> None:
    run1 = captured_run(store, when=T0)
    run2 = store.ensure_run(
        "ote_idm_soap",
        T0 + timedelta(minutes=15),
        state="captured",
        origin="scheduled",
        capture_id="c2",
        now=NOW,
    ).id
    store.commit(
        claim(store, run1),
        state="processed",
        outcome="ok",
        derivation=D_A,
        observations=[obs(sha=SHA_1)],
        now=NOW,
    )
    store.commit(
        claim(store, run2),
        state="processed",
        outcome="ok",
        derivation=D_B,
        observations=[obs(sha=SHA_2, derivation=D_B)],
        now=NOW,
    )
    assert [r.id for r in store.runs_with_derivation(D_A.derivation_id)] == [run1]
    assert [r.id for r in store.runs_with_derivation(D_B.derivation_id)] == [run2]
    assert store.runs_with_derivation("0000000000000000") == ()


def test_record_attempt_and_set_state_for_unleased_verbs(store: Store) -> None:
    run = store.ensure_run("t", T0, state="missing_capture", origin="backfill", now=NOW)
    a = store.record_attempt(
        run.id, "backfill", outcome="source_unavailable", error="HTTP 503", now=NOW
    )
    assert a.kind == "backfill" and a.outcome == "source_unavailable" and a.lease_owner is None
    assert store.set_state(run.id, "unrecoverable", now=NOW).state == "unrecoverable"
    assert store.runs("t", since=T0, until=T0 + timedelta(minutes=1))[0].id == run.id
    assert store.runs("t", since=T0 + timedelta(minutes=1)) == ()


def test_derivation_registration_is_idempotent_and_keeps_the_first_time(store: Store) -> None:
    first = store.register_derivation(D_A, now=NOW)
    second = store.register_derivation(D_A, now=NOW + TTL)
    assert first.registered_at == second.registered_at == NOW
    assert store.derivation(D_A.derivation_id) == first
    assert store.derivation("0000000000000000") is None
    assert first.mapping_block == {"m": "a"} and first.parser_ref == "generic:soap@0.0.1"
