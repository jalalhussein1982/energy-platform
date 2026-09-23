"""ADR-033 §3 correction re-poll and the P5-D6 crash-matrix row: a forced attempt whose payload
changed is pending again; an unchanged one is a poll."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from energy_platform.runtime import capture, last_run_of_day, process, recapture
from tests.runtime.harness import DAY, SCHEDULED, T1, Clock, runtime
from tests.synthetic import ote_im_price_period_response

# runs on three consecutive delivery days at 00:15 Prague (22:15 UTC the evening before)
RUNS = [SCHEDULED + timedelta(days=d) for d in range(3)]
NOW = SCHEDULED + timedelta(days=3, hours=2)  # 00:15 Prague on the 4th day → D-1 … D-3 exist


def seeded() -> tuple[object, Clock]:
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T1, clock=clock)
    for when in RUNS:
        clock.now = when + timedelta(minutes=1)
        assert capture(rt, when).outcome == "ok"
    process(rt)
    clock.now = NOW
    return rt, clock


def test_last_run_of_day_finds_the_newest_scheduled_for() -> None:
    rt, _ = seeded()
    assert last_run_of_day(rt, DAY) == RUNS[0]  # type: ignore[arg-type]
    assert last_run_of_day(rt, DAY + timedelta(days=2)) == RUNS[2]  # type: ignore[arg-type]
    assert last_run_of_day(rt, DAY + timedelta(days=9)) is None  # type: ignore[arg-type]


def test_recapture_forces_a_new_attempt_on_each_past_day() -> None:
    rt, _ = seeded()
    reports = recapture(rt, days=3)  # type: ignore[arg-type]
    assert [r.delivery_day for r in reports] == [DAY + timedelta(days=d) for d in (2, 1, 0)]
    assert all(not r.skipped for r in reports)
    for r in reports:
        assert r.capture is not None and r.capture.outcome == "ok" and r.capture.created
        assert r.capture.entry is not None and r.capture.entry.attempt == 2
        assert r.capture.entry.content_changed is False  # same synthetic payload


def test_a_day_without_a_run_is_skipped_not_invented() -> None:
    rt, _ = seeded()
    reports = recapture(rt, days=5)  # type: ignore[arg-type]
    assert [r.skipped for r in reports] == [False, False, False, True, True]
    assert reports[-1].scheduled_for is None and reports[-1].capture is None


def test_days_below_one_is_refused() -> None:
    rt, _ = seeded()
    with pytest.raises(ValueError, match="days"):
        recapture(rt, days=0)  # type: ignore[arg-type]


def test_row_9_unchanged_forced_attempt_is_a_poll_not_pending() -> None:
    """P5-D6 (a): identical payload → attempt recorded, run stays ``processed``."""
    rt, _ = seeded()
    recapture(rt, days=1)  # type: ignore[arg-type]
    run = rt.store.get_run("ote_idm_soap", RUNS[2])  # type: ignore[attr-defined]
    assert run is not None and run.state == "processed"
    kinds = [a.kind for a in rt.store.attempts(run.id)]  # type: ignore[attr-defined]
    assert kinds == ["capture", "process", "capture"]
    assert process(rt) == ()  # type: ignore[arg-type]


def test_row_10_changed_forced_attempt_is_pending_and_processed_again() -> None:
    """P5-D6 (b): a correction with new content lowers the run to ``captured``; the next
    ``process`` claims it and Silver gains the corrected version (ADR-023 identity)."""
    clock = Clock(SCHEDULED + timedelta(minutes=1))
    corrected = False

    def payload() -> bytes:
        body = ote_im_price_period_response(DAY)
        return body.replace(b"170.13", b"171.99") if corrected else body

    rt = runtime(T1, payload=payload, clock=clock)
    assert capture(rt, SCHEDULED).outcome == "ok"
    assert process(rt)[0].inserted == 2 * 96
    corrected = True
    clock.now = NOW
    reports = recapture(rt, days=3)
    changed = [r for r in reports if r.capture is not None]
    assert len(changed) == 1 and changed[0].capture is not None
    assert changed[0].capture.entry is not None and changed[0].capture.entry.content_changed
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "captured"
    assert run.capture_id == changed[0].capture.entry.capture_id
    again = process(rt)
    assert len(again) == 1 and again[0].outcome == "ok"
    run = rt.store.get_run("ote_idm_soap", SCHEDULED)
    assert run is not None and run.state == "processed"
    current = rt.store.current_rows("ote.idm_continuous", metric="price_vwap")
    assert current[0].value == Decimal("171.99")
    assert current[0].observation.fetched_at > datetime(2026, 9, 18, tzinfo=UTC)


def test_a_correction_compares_with_its_own_day_not_the_newest_run() -> None:
    """The conditional validators, a 304's payload and content_changed come from the same
    delivery day's last real capture, never from the target's newest run (another day's
    file): 2026-09-23 on the demo a 304 attached today's XLSX to runs of 21 and 22 September."""
    from energy_platform.bronze import sha256_hex
    from energy_platform.fetch import Fetcher
    from energy_platform.fetch.offline import Request, Response, mock_transport
    from tests.runtime.harness import T2, payload_for

    sent: list[str | None] = []
    files: dict[str, bytes] = {}  # one file per day: a generated XLSX is not byte-stable

    def server(req: Request) -> Response:
        if req.url.path.startswith("/en/"):
            return Response(200, content=b"<html>no link</html>")  # the day's template is used
        day = req.url.path.split("/")[-1][9:19]  # IM_15MIN_DD_MM_YYYY_EN.xlsx
        sent.append(req.headers.get("if-none-match"))
        if req.headers.get("if-none-match") is not None:
            return Response(304)  # a server that answers 304 to any validator
        d = datetime.strptime(day, "%d_%m_%Y").date()  # noqa: DTZ007 (a date, no time)
        body = files.setdefault(day, payload_for(T2, d))
        return Response(200, content=body, headers={"etag": f'"{day}"'})

    def factory(manifest: object) -> Fetcher:
        return Fetcher(
            allowed_hosts=T2.allowed_hosts,
            transport=mock_transport(server),
            offline=True,
            sleep=lambda s: None,
        )

    clock = Clock(SCHEDULED + timedelta(minutes=1))
    rt = runtime(T2, clock=clock)
    object.__setattr__(rt, "fetcher_factory", factory)
    first, second = RUNS[0], RUNS[1]
    for when in (first, second):
        clock.now = when + timedelta(minutes=1)
        assert capture(rt, when).outcome == "ok"
    own = rt.bronze.log.entries_for(T2.target_id, first)[-1]
    clock.now = NOW
    again = capture(rt, first, force=True)
    assert again.entry is not None
    next_day = rt.bronze.log.entries_for(T2.target_id, second)[-1]
    # a new day sends no validator of another day's file and gets its own content
    assert sent[:2] == [None, None]
    assert next_day.payload_sha256 == sha256_hex(files[f"{DAY + timedelta(days=1):%d_%m_%Y}"])
    # the correction of the first day sends that day's validator; the 304 means that day's file
    assert sent[2] == f'"{DAY:%d_%m_%Y}"'
    assert again.entry.payload_sha256 == own.payload_sha256 == sha256_hex(files[f"{DAY:%d_%m_%Y}"])
    assert again.entry.content_changed is False
