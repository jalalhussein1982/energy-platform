"""Review 3 (2026-09-25, codex-astra) counterexamples as negative tests.

Each test is the reviewer's probe (``codex-review/evidence/*.py``) with its assertion turned
around: the probe asserted the defect, the test asserts the fix. R2 (the schedule's instant),
R4 (the implementation inside the derivation identity), R5 and R6 (the drill's cohort and its
value guarantee). Store-level halves that must hold on PostgreSQL live in ``tests/store``.
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import energy_platform
from energy_platform import implementation_version, source_digest
from energy_platform.bronze import Bronze, MemoryBlobStore, MemoryCaptureLog
from energy_platform.bronze.fixtures import load_fixture
from energy_platform.contracts.manifest import Manifest, load_manifest
from energy_platform.mapping import MappingContext, MappingResult
from energy_platform.parse import parser_ref
from energy_platform.runtime import (
    Runtime,
    backfill,
    capture,
    detect_gaps,
    instant_from_job_name,
    intended_instant,
    latest_instant,
    process,
    replay_range,
    restore_drill,
)
from energy_platform.runtime.process import map_payload
from energy_platform.store import MemoryStore, derivation_for
from tests.runtime.harness import SCHEDULED, T1, Clock, runtime

PRAGUE = "Europe/Prague"

# ---------------------------------------------------------------------------- R2: the instant


def test_r2_a_capture_started_25_seconds_late_serves_its_tick_and_nothing_is_refetched() -> None:
    """The reviewer's ``schedule_probe.py`` inverted: the pod starts 25.69 s after its tick.
    Keyed by the schedule's instant, the capture is the tick's; the gap detector finds no
    phantom and the backfill has nothing to fetch — one Bronze entry, one source read."""
    actual_start = SCHEDULED + timedelta(seconds=25, microseconds=693263)
    clock = Clock(actual_start)
    rt = runtime(clock=clock)
    when = intended_instant(rt.manifest, actual_start)
    assert when == SCHEDULED
    assert capture(rt, when).outcome == "ok"
    assert process(rt)[0].outcome == "ok"
    clock.now = SCHEDULED + timedelta(minutes=31)
    gaps = detect_gaps(rt, lookback=timedelta(minutes=31, seconds=1))
    assert [g.kind for g in gaps if g.scheduled_for == SCHEDULED] == []
    assert all(g.kind == "pending" for g in gaps)
    assert backfill(rt, limit=1) == ()
    assert len(rt.bronze.log.list(rt.target_id)) == 1


def test_r2_the_controllers_tick_is_read_from_the_job_name() -> None:
    """A CronJob-created Job is named ``<cronjob>-<minutes since the epoch>`` of its scheduled
    time: the demo's own Job name decodes to its tick, and the tick wins over the wall clock
    even when the pod starts so late that the next tick has passed."""
    name = "energy-platform-capture-ceps-load-29838195"
    tick = instant_from_job_name(name)
    assert tick == datetime(2026, 9, 24, 23, 15, tzinfo=UTC)
    late = tick + timedelta(minutes=20, seconds=3)  # past the 23:30 tick of a */15 cadence
    assert intended_instant(T1, late, name) == tick
    assert intended_instant(T1, late, None) == tick + timedelta(minutes=15)  # the fallback


def test_r2_a_job_name_without_a_valid_tick_falls_back_to_the_newest_firing_instant() -> None:
    now = SCHEDULED + timedelta(seconds=40)
    assert instant_from_job_name("restore-drill-manual-3") is None
    assert instant_from_job_name(None) is None and instant_from_job_name("") is None
    assert intended_instant(T1, now, "restore-drill-manual-3") == SCHEDULED
    # a suffix that decodes to an instant the cadence never fires at (23:17 for */15)
    off_grid = int((SCHEDULED + timedelta(minutes=2)).timestamp()) // 60
    assert intended_instant(T1, now + timedelta(minutes=2), f"x-{off_grid}") == SCHEDULED
    # a tick from another day is not this run's identity
    stale = int((SCHEDULED - timedelta(days=2)).timestamp()) // 60
    assert intended_instant(T1, now, f"x-{stale}") == SCHEDULED
    # a tick in the future (a clock skew) is refused too
    ahead = int((SCHEDULED + timedelta(minutes=15)).timestamp()) // 60
    assert intended_instant(T1, now, f"x-{ahead}") == SCHEDULED


def test_r2_a_genuinely_missed_tick_is_still_detected() -> None:
    """The fallback never invents an older instant: the 22:15 tick had no capture, the 22:30
    pod captures 22:30, and the detector still reports 22:15 as missing."""
    clock = Clock(SCHEDULED + timedelta(minutes=15, seconds=9))
    rt = runtime(clock=clock)
    when = intended_instant(rt.manifest, clock.now)
    assert when == SCHEDULED + timedelta(minutes=15)
    assert capture(rt, when).outcome == "ok"
    process(rt)
    clock.now = SCHEDULED + timedelta(minutes=46)
    gaps = {g.scheduled_for: g.kind for g in detect_gaps(rt, lookback=timedelta(minutes=47))}
    assert gaps[SCHEDULED] == "missing_capture"
    assert SCHEDULED + timedelta(minutes=15) not in gaps  # served, processed: nothing to say


def test_r2_the_instant_follows_the_cadence_timezone_and_dst() -> None:
    """A ``15 13-16 * * *`` Prague cadence at 11:20Z is the 13:15 local tick (11:15Z); on the
    autumn change-over day the two 02:30 local instants are distinct UTC instants."""
    daily = T1.model_copy(
        update={"cadence": T1.cadence.model_copy(update={"cron": "15 13-16 * * *"})}
    )
    assert intended_instant(daily, datetime(2026, 9, 24, 11, 20, tzinfo=UTC)) == datetime(
        2026, 9, 24, 11, 15, tzinfo=UTC
    )
    # 2026-10-25: 02:31 CEST is 00:31Z, 02:31 CET an hour later is 01:31Z
    assert intended_instant(T1, datetime(2026, 10, 25, 0, 31, tzinfo=UTC)) == datetime(
        2026, 10, 25, 0, 30, tzinfo=UTC
    )
    assert intended_instant(T1, datetime(2026, 10, 25, 1, 31, tzinfo=UTC)) == datetime(
        2026, 10, 25, 1, 30, tzinfo=UTC
    )
    # a monthly cadence is found across the month boundary; a never-firing one floors now
    monthly = latest_instant("37 7 1 * *", PRAGUE, datetime(2026, 9, 24, 12, 0, tzinfo=UTC))
    assert monthly == datetime(2026, 9, 1, 5, 37, tzinfo=UTC)
    assert latest_instant("0 0 30 2 *", PRAGUE, datetime(2026, 9, 24, 12, 0, tzinfo=UTC)) is None
    never = T1.model_copy(update={"cadence": T1.cadence.model_copy(update={"cron": "0 0 30 2 *"})})
    assert intended_instant(never, datetime(2026, 9, 24, 12, 0, 7, tzinfo=UTC)) == datetime(
        2026, 9, 24, 12, 0, tzinfo=UTC
    )


# ------------------------------------------------------------- R4: the implementation identity


def test_r4_the_digest_follows_the_package_bytes_and_ignores_bytecode(tmp_path: Path) -> None:
    """ADR-023 amendment 3: an unchanged copy of the package has the same digest as the
    installed one; one byte changed in a mapping module changes it; bytecode does not count."""
    copy = tmp_path / "energy_platform"
    shutil.copytree(Path(energy_platform.__file__).parent, copy, ignore=_no_pycache)
    assert source_digest(copy) == source_digest()
    assert re.fullmatch(r"0\.0\.1\+[0-9a-f]{12}", implementation_version())
    (copy / "__pycache__").mkdir()
    (copy / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\0\0")
    source_digest.cache_clear()
    assert source_digest(copy) == source_digest()
    target = copy / "mapping" / "__init__.py"
    target.write_bytes(target.read_bytes() + b"\n# a one-line fix\n")
    source_digest.cache_clear()
    assert source_digest(copy) != source_digest()


def _no_pycache(directory: str, names: list[str]) -> set[str]:
    return {n for n in names if n == "__pycache__"}


def _first_price(rt: Runtime) -> Decimal | None:
    rows = rt.store.current_rows(rt.manifest.contract.dataset_id)
    return next(r.value for r in rows if r.observation.metric == "price_vwap")


def test_r4_a_corrected_implementation_replays_as_a_new_derivation_and_the_same_one_is_a_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewer's ``derivation_probe.py`` inverted. A core-only correction (the mapper's
    result differs by 1, manifest and payload unchanged) is another implementation, hence
    another digest: the replay inserts the corrected versions under a new derivation and the
    current view shows them. The same implementation replayed again inserts nothing."""
    rt = runtime()
    assert capture(rt, SCHEDULED).outcome == "ok"
    assert process(rt)[0].inserted == 192
    old = derivation_for(rt.manifest, parser_ref(rt.manifest)).derivation_id
    before = _first_price(rt)
    assert before is not None

    def corrected(manifest: Manifest, payload: bytes, ctx: MappingContext) -> MappingResult:
        r = map_payload(manifest, payload, ctx)
        fixed = tuple(
            o.model_copy(update={"value": o.value + Decimal("1")})
            if o.metric == "price_vwap" and o.value is not None
            else o
            for o in r.observations
        )
        return MappingResult(fixed, r.events)

    # the fix changes the package's bytes: another digest, whatever __version__ says
    monkeypatch.setattr(energy_platform, "implementation_version", lambda: "0.0.1+f1x3d000000")
    monkeypatch.setattr(sys.modules["energy_platform.runtime.process"], "map_payload", corrected)
    new = derivation_for(rt.manifest, parser_ref(rt.manifest)).derivation_id
    assert new != old
    rt.clock.advance(timedelta(seconds=1))  # type: ignore[attr-defined]
    replay_range(rt, SCHEDULED, SCHEDULED + timedelta(minutes=1))
    good = process(rt)
    assert good[0].outcome == "ok" and good[0].inserted == 192
    assert _first_price(rt) == before + Decimal("1")
    stored = rt.store.derivation(new)
    assert stored is not None and stored.platform_version == "0.0.1+f1x3d000000"
    # the same implementation again: an exact retry, nothing inserted, value unchanged
    rt.clock.advance(timedelta(seconds=1))  # type: ignore[attr-defined]
    replay_range(rt, SCHEDULED, SCHEDULED + timedelta(minutes=1))
    again = process(rt)
    assert again[0].outcome == "noop" and again[0].inserted == 0
    assert _first_price(rt) == before + Decimal("1")


# ------------------------------------------------- R5 / R6: the drill's cohort and its guarantee


def _settlement_live() -> tuple[MemoryStore, Bronze, tuple[Manifest, ...], Clock]:
    """The reviewer's ``recovery_probes.py`` setting: two committed targets sharing
    ``ote.imbalance_settlement`` over SOAP, each processed from its committed fixture."""
    store = MemoryStore()
    bronze = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    manifests = []
    for target, fixture in (
        ("ote_imbalance_settlement", "ordinary_day"),
        ("ote_imbalance_settlement_monthly", "march_2026_month"),
    ):
        m = load_manifest(Path("targets") / target / "manifest.yaml")
        entry, payload = load_fixture(Path("targets") / target / "fixtures" / fixture)
        bronze.ingest(entry, payload)
        rt = runtime(
            m,
            store=store,
            bronze=bronze,
            clock=Clock(entry.fetched_at + timedelta(minutes=1)),
            payload=payload,
        )
        reports = process(rt)
        assert reports and all(r.outcome in {"ok", "noop"} for r in reports), reports
        manifests.append(m)
    newest = max(e.fetched_at for m in manifests for e in bronze.log.list(m.target_id))
    return store, bronze, tuple(manifests), Clock(newest + timedelta(days=1))


def test_r5_targets_sharing_a_dataset_pass_a_fresh_rebuild_in_either_order() -> None:
    """The reviewer's shared-dataset probe inverted: on an EMPTY scratch store the first drill
    passes, whichever target comes first, and each target's counts are its own — the daily
    target's 288 versions, the monthly's 8 916 — never the sibling's rows read as loss or as
    pending work."""
    live, replica, manifests, clock = _settlement_live()
    for order in (manifests, tuple(reversed(manifests))):
        report = restore_drill(
            order, scratch=MemoryStore(), replica=replica, live=live, clock=clock
        )
        assert report.ok, [t.message for t in report.targets]
        by_id = {t.target_id: t for t in report.targets}
        daily, monthly = (
            by_id["ote_imbalance_settlement"],
            by_id["ote_imbalance_settlement_monthly"],
        )
        assert daily.live is not None and daily.live.rows == 288 and daily.scratch == daily.live
        assert monthly.live is not None and monthly.live.rows == 8916
        assert monthly.scratch == monthly.live
        for t in (daily, monthly):
            assert t.missing_versions == t.extra_versions == t.diverging_versions == 0
            assert t.sibling_versions == 0 and t.message.startswith("identical")


def test_r5_a_target_with_no_captures_reports_no_versions_of_its_siblings() -> None:
    """The saved live drill claimed 576 versions for two monthly targets with zero captures:
    a target that never captured reports nothing, not its siblings' rows."""
    live, replica, manifests, clock = _settlement_live()
    final = load_manifest(Path("targets/ote_imbalance_settlement_final/manifest.yaml"))
    report = restore_drill(
        (*manifests, final), scratch=MemoryStore(), replica=replica, live=live, clock=clock
    )
    assert report.ok
    t = report.targets[-1]
    assert t.target_id == final.target_id and t.replica_entries == 0
    assert t.live is not None and t.live.rows == 0 and t.scratch is not None
    assert t.scratch.rows == 0 and t.message == "identical: 0 Silver versions"


def test_r6_a_value_preserving_mapping_revision_is_history_not_loss() -> None:
    """The reviewer's mapping-revision probe inverted: ``ignore_fields`` gains an unused name,
    the derivation changes as designed, live holds 384 versions across two derivations, and a
    fresh current-manifest rebuild PASSES — the 192 versions under the retired derivation are
    history the physical backup keeps, named as such, not loss."""
    rt = runtime(T1)
    assert capture(rt, SCHEDULED).outcome == "ok"
    assert process(rt)[0].outcome == "ok"
    changed = T1.model_copy(
        update={
            "mapping": T1.mapping.model_copy(
                update={"ignore_fields": (*T1.mapping.ignore_fields, "DisplayNote")}
            )
        }
    )
    rt2 = runtime(changed, store=rt.store, bronze=rt.bronze, clock=rt.clock)  # type: ignore[arg-type]
    old_d = derivation_for(T1, parser_ref(T1)).derivation_id
    new_d = derivation_for(changed, parser_ref(changed)).derivation_id
    assert old_d != new_d
    rt.clock.advance(timedelta(seconds=1))  # type: ignore[attr-defined]
    replay_range(rt2, SCHEDULED, SCHEDULED + timedelta(minutes=1))
    process(rt2)
    assert len(rt.store.all_rows(T1.contract.dataset_id)) == 384
    report = restore_drill(
        [changed], scratch=MemoryStore(), replica=rt.bronze, live=rt.store, clock=rt.clock
    )
    t = report.targets[0]
    assert report.ok, t.message
    assert t.live is not None and t.live.rows == 192 and t.scratch is not None
    assert t.scratch.rows == 192 and t.missing_versions == 0 and t.diverging_versions == 0
    assert t.historical_versions == 192 and t.historical_derivations == 1
    assert "192 version(s) under 1 retired derivation(s) not compared" in t.message


def test_r6_a_value_changing_implementation_diverges_until_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the guarantee: when the running implementation produces another value
    from the same payload than live's newest derivation, the drill FAILS and names it as
    divergence (not loss); once the correction is replayed, the drill passes and the old
    values are history."""
    rt = runtime(T1)
    assert capture(rt, SCHEDULED).outcome == "ok"
    assert process(rt)[0].inserted == 192

    def corrected(manifest: Manifest, payload: bytes, ctx: MappingContext) -> MappingResult:
        r = map_payload(manifest, payload, ctx)
        fixed = tuple(
            o.model_copy(update={"value": o.value + Decimal("1")})
            if o.metric == "price_vwap" and o.value is not None
            else o
            for o in r.observations
        )
        return MappingResult(fixed, r.events)

    monkeypatch.setattr(energy_platform, "implementation_version", lambda: "0.0.1+f1x3d000000")
    monkeypatch.setattr(sys.modules["energy_platform.runtime.process"], "map_payload", corrected)
    rt.clock.advance(timedelta(seconds=1))  # type: ignore[attr-defined]
    before = restore_drill(
        [T1], scratch=MemoryStore(), replica=rt.bronze, live=rt.store, clock=rt.clock
    )
    t = before.targets[0]
    assert not before.ok and t.diverging_versions == 96 and t.missing_versions == 0
    assert "have another value under the running implementation" in t.message
    # the ADR-016 §4 repair: replay; the corrected versions outrank the old ones
    replay_range(rt, SCHEDULED, SCHEDULED + timedelta(minutes=1))
    # every row is a new version under the new derivation (the key carries it, ADR-023 §2),
    # 96 with the corrected price and 96 with the unchanged volume
    assert process(rt)[0].inserted == 192
    after = restore_drill(
        [T1], scratch=MemoryStore(), replica=rt.bronze, live=rt.store, clock=rt.clock
    )
    t = after.targets[0]
    assert after.ok, t.message
    assert t.diverging_versions == 0 and t.historical_versions == 192
    assert t.historical_derivations == 1
