"""Bronze: blob-then-entry order, idempotency, content_changed, 304, hot/cold read, fixtures."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock

import pytest

from energy_platform.bronze import (
    Bronze,
    BronzeError,
    CaptureEntry,
    CaptureOutcome,
    FileBlobStore,
    FileCaptureLog,
    Invalidation,
    MemoryBlobStore,
    MemoryCaptureLog,
    blob_key,
    entry_key,
    import_fixture,
    load_fixture,
    sha256_hex,
    write_fixture,
)
from energy_platform.fetch.client import FetchResult

T0 = datetime(2026, 9, 17, 22, 0, tzinfo=UTC)


def result(
    body: bytes, *, status: int = 200, not_modified: bool = False, etag: str | None = None
) -> FetchResult:
    return FetchResult(
        url="https://www.ote-cr.cz/pw-data/services/PublicDataService",
        status=status,
        headers={},
        body=body,
        content_type="text/xml",
        fetched_at=T0 + timedelta(minutes=5),
        etag=etag,
        last_modified=None,
        not_modified=not_modified,
        hops=("https://www.ote-cr.cz/pw-data/services/PublicDataService",),
    )


def bronze() -> tuple[Bronze, MemoryBlobStore, MemoryCaptureLog]:
    blobs, log = MemoryBlobStore(), MemoryCaptureLog()
    return Bronze(blobs, log), blobs, log


def test_capture_writes_blob_then_entry_with_the_01_envelope_fields() -> None:
    b, blobs, log = bronze()
    out = b.capture(
        target_id="ote_idm_soap", scheduled_for=T0, result=result(b"<r/>"), transport="soap"
    )
    e = out.entry
    assert out.created is True
    assert e.capture_id == "ote_idm_soap:2026-09-17T220000Z:1"
    assert e.key == "captures/ote_idm_soap/2026/09/17/2026-09-17T220000Z_1.json"
    assert e.payload_sha256 == sha256_hex(b"<r/>")
    assert (
        e.raw_ref
        == blob_key(e.payload_sha256)
        == f"bronze/blobs/{e.payload_sha256[:2]}/{e.payload_sha256}"
    )
    assert e.content_changed is True and e.attempt == 1 and e.tier == "hot"
    assert e.fetched_at == T0 + timedelta(minutes=5) and e.http_status == 200
    assert blobs.get(e.payload_sha256) == b"<r/>" and log.get(e.capture_id) == e


def test_entry_key_uses_the_utc_day_of_scheduled_for() -> None:
    prague = datetime.fromisoformat("2026-09-18T00:00:00+02:00")
    assert entry_key("t", prague, 1) == "captures/t/2026/09/17/2026-09-17T220000Z_1.json"


def test_second_capture_of_the_same_instant_is_a_no_op_unless_forced() -> None:
    b, blobs, log = bronze()
    first = b.capture(target_id="t", scheduled_for=T0, result=result(b"a"), transport="soap")
    again = b.capture(target_id="t", scheduled_for=T0, result=result(b"b"), transport="soap")
    assert again.created is False and again.entry == first.entry
    assert len(blobs) == 1
    forced = b.capture(
        target_id="t", scheduled_for=T0, result=result(b"b"), transport="soap", force=True
    )
    assert forced.created is True and forced.entry.attempt == 2
    assert [e.attempt for e in log.entries_for("t", T0)] == [1, 2]


def test_unchanged_payload_makes_a_new_entry_but_no_new_blob() -> None:
    b, blobs, log = bronze()
    b.capture(target_id="t", scheduled_for=T0, result=result(b"same"), transport="soap")
    second = b.capture(  # the next run of the same day; the runtime passes it as the baseline
        target_id="t",
        scheduled_for=T0 + timedelta(minutes=15),
        result=result(b"same"),
        transport="soap",
        baseline=log.list("t")[-1],
    ).entry
    assert second.content_changed is False
    assert len(blobs) == 1 and len(log.list("t")) == 2
    assert second.raw_ref == log.list("t")[0].raw_ref


def test_304_reuses_the_previous_blob_and_validators() -> None:
    b, blobs, log = bronze()
    b.capture(target_id="t", scheduled_for=T0, result=result(b"x", etag='"e1"'), transport="xlsx")
    nm = b.capture(
        target_id="t",
        scheduled_for=T0 + timedelta(minutes=15),
        result=result(b"", status=304, not_modified=True),
        transport="xlsx",
        baseline=log.list("t")[-1],
    ).entry
    assert nm.http_status == 304 and nm.content_changed is False
    assert nm.payload_sha256 == sha256_hex(b"x") and nm.etag == '"e1"' and nm.size == 1
    assert len(blobs) == 1


def test_304_without_a_previous_capture_is_an_error() -> None:
    b, _, _ = bronze()
    with pytest.raises(BronzeError, match="304"):
        b.capture(
            target_id="t",
            scheduled_for=T0,
            result=result(b"", status=304, not_modified=True),
            transport="xlsx",
        )


def test_304_for_another_resource_than_the_baseline_is_refused() -> None:
    """A 304 means "the same as the baseline": only if the baseline fetched the same URL."""
    b, _, log = bronze()
    b.capture(target_id="t", scheduled_for=T0, result=result(b"x", etag='"e1"'), transport="xlsx")
    other = FetchResult(
        url="https://www.ote-cr.cz/another-day.xlsx",
        status=304,
        headers={},
        body=b"",
        content_type=None,
        fetched_at=T0 + timedelta(minutes=20),
        etag=None,
        last_modified=None,
        not_modified=True,
        hops=("https://www.ote-cr.cz/another-day.xlsx",),
    )
    with pytest.raises(BronzeError, match="different resource"):
        b.capture(
            target_id="t",
            scheduled_for=T0 + timedelta(minutes=15),
            result=other,
            transport="xlsx",
            baseline=log.list("t")[-1],
        )


def test_read_tries_hot_then_cold_and_reports_the_tier() -> None:
    hot, cold, log = MemoryBlobStore(), MemoryBlobStore(), MemoryCaptureLog()
    b = Bronze(hot, log, cold=cold)
    sha = cold.put(b"archived")
    obj = b.read(blob_key(sha))
    assert (obj.payload, obj.tier) == (b"archived", "cold")
    hot.put(b"fresh")
    assert b.read(blob_key(sha256_hex(b"fresh"))).tier == "hot"
    with pytest.raises(BronzeError, match="missing"):
        b.read(blob_key("0" * 64))


def test_read_verifies_the_content_address() -> None:
    class Lying(MemoryBlobStore):
        def get(self, sha256: str) -> bytes | None:
            return b"tampered"

    b = Bronze(Lying(), MemoryCaptureLog())
    with pytest.raises(BronzeError, match="does not match"):
        b.read(blob_key(sha256_hex(b"original")))


def test_a_failing_log_leaves_only_a_harmless_orphan_blob() -> None:
    """ADR-024 §6 row 1: crash after blob PUT, before entry PUT."""

    class Dead(MemoryCaptureLog):
        def put(self, entry: CaptureEntry) -> None:
            raise OSError("object store unreachable")

    blobs = MemoryBlobStore()
    b = Bronze(blobs, Dead())
    with pytest.raises(OSError, match="unreachable"):
        b.capture(target_id="t", scheduled_for=T0, result=result(b"payload"), transport="soap")
    assert len(blobs) == 1  # orphan, content-addressed
    healthy = Bronze(blobs, MemoryCaptureLog())
    out = healthy.capture(
        target_id="t", scheduled_for=T0, result=result(b"payload"), transport="soap"
    )
    assert out.created is True and len(blobs) == 1  # same address, nothing duplicated


def test_file_backends_round_trip_and_list_by_window(tmp_path: Path) -> None:
    b = Bronze(FileBlobStore(tmp_path), FileCaptureLog(tmp_path))
    for i in range(3):
        b.capture(
            target_id="t",
            scheduled_for=T0 + timedelta(minutes=15 * i),
            result=result(f"p{i}".encode()),
            transport="soap",
        )
    assert (tmp_path / "captures/t/2026/09/17/2026-09-17T220000Z_1.json").exists()
    assert (tmp_path / blob_key(sha256_hex(b"p0"))).read_bytes() == b"p0"
    log = FileCaptureLog(tmp_path)
    window = log.list("t", since=T0 + timedelta(minutes=15), until=T0 + timedelta(minutes=45))
    assert [e.scheduled_for for e in window] == [
        T0 + timedelta(minutes=15),
        T0 + timedelta(minutes=30),
    ]
    latest = log.latest("t")
    assert latest is not None and latest.scheduled_for == T0 + timedelta(minutes=30)
    assert log.get("t:2026-09-17T221500Z:1") is not None
    assert Bronze(FileBlobStore(tmp_path), log).read(window[0].raw_ref).payload == b"p1"


def test_fixture_is_a_bronze_object(tmp_path: Path) -> None:
    b, _, _ = bronze()
    entry = b.capture(
        target_id="t", scheduled_for=T0, result=result(b"<r/>"), transport="soap"
    ).entry
    write_fixture(tmp_path / "fx", entry, b"<r/>")
    assert sorted(p.name for p in (tmp_path / "fx").iterdir()) == ["blob", "entry.json"]
    loaded, payload = load_fixture(tmp_path / "fx")
    assert loaded == entry and payload == b"<r/>"
    with pytest.raises(BronzeError):
        write_fixture(tmp_path / "bad", entry, b"other")
    target = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    assert import_fixture(target, tmp_path / "fx") == entry
    assert target.read(entry.raw_ref).payload == b"<r/>"
    assert target.verify(entry) is True


def test_entry_json_round_trip_keeps_aware_utc_datetimes() -> None:
    b, _, _ = bronze()
    entry = b.capture(
        target_id="t", scheduled_for=T0, result=result(b"<r/>"), transport="soap"
    ).entry
    again = CaptureEntry.from_json(entry.to_json())
    assert again == entry and again.scheduled_for.tzinfo is not None


def test_review2_dc06_two_concurrent_writers_keep_two_entries() -> None:
    """Review 2 DC-06 (ADR-024 amendment 3): both writers list the same attempts before either
    writes; the loser's create fails on the key and it takes the next attempt number — two
    blobs, two entries, two capture ids, nothing overwritten."""
    barrier = Barrier(2)

    class Racing(MemoryCaptureLog):
        """Both writers' *first* listing waits for the other, so both compute attempt 1."""

        def __init__(self) -> None:
            super().__init__()
            self._first_listings = 2
            self._gate = Lock()

        def entries_for(self, target_id: str, scheduled_for: datetime) -> tuple[CaptureEntry, ...]:
            snapshot = super().entries_for(target_id, scheduled_for)
            with self._gate:
                synchronise = self._first_listings > 0
                self._first_listings -= 1
            if synchronise:
                barrier.wait(timeout=5)
            return snapshot

    blobs, log = MemoryBlobStore(), Racing()
    b = Bronze(blobs, log)

    def one(body: bytes) -> CaptureOutcome:
        return b.capture(target_id="t", scheduled_for=T0, result=result(body), transport="soap")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(one, (b"first observation", b"second observation")))
    assert all(o.created for o in outcomes)
    assert {o.entry.capture_id for o in outcomes} == {
        "t:2026-09-17T220000Z:1",
        "t:2026-09-17T220000Z:2",
    }
    assert len(log.list("t")) == 2 and len(blobs) == 2
    assert {e.payload_sha256 for e in log.list("t")} == {o.entry.payload_sha256 for o in outcomes}


def test_review2_dc06_file_log_create_is_exclusive(tmp_path: Path) -> None:
    log = FileCaptureLog(tmp_path)
    b = Bronze(FileBlobStore(tmp_path), log)
    first = b.capture(target_id="t", scheduled_for=T0, result=result(b"a"), transport="soap")
    assert first.created and log.put_new(first.entry) is False  # the key exists: refused
    stored = log.get(first.entry.capture_id)
    assert stored is not None and stored.payload_sha256 == first.entry.payload_sha256
    again = b.capture(
        target_id="t", scheduled_for=T0, result=result(b"b"), transport="soap", force=True
    )
    assert again.entry.attempt == 2 and len(log.entries_for("t", T0)) == 2


def test_capture_gives_up_after_repeated_collisions() -> None:
    class Taken(MemoryCaptureLog):
        def put_new(self, entry: CaptureEntry) -> bool:
            return False  # someone else always wins

    b = Bronze(MemoryBlobStore(), Taken())
    with pytest.raises(BronzeError, match="collided"):
        b.capture(target_id="t", scheduled_for=T0, result=result(b"x"), transport="soap")


def test_invalidation_objects_are_create_only_and_listed_per_target(tmp_path: Path) -> None:
    """ADR-038: one immutable JSON object per decision, beside the capture log, on both
    offline backends; the key names the capture and, when scoped, the derivation."""
    decision = Invalidation(
        target_id="t",
        capture_id="t:2026-09-17T220000Z:1",
        derivation_id=None,
        reason="wrong day",
        recorded_by="maintainer",
        recorded_at=T0,
    )
    scoped = decision.model_copy(update={"derivation_id": "a" * 16})
    assert decision.key == "invalidations/t/2026-09-17T220000Z_1.json"
    assert scoped.key == "invalidations/t/2026-09-17T220000Z_1.aaaaaaaaaaaaaaaa.json"
    for log in (MemoryCaptureLog(), FileCaptureLog(tmp_path)):
        assert log.put_invalidation(decision) is True
        assert log.put_invalidation(decision) is False
        assert log.put_invalidation(scoped) is True
        assert set(log.invalidations("t")) == {decision, scoped}  # listed, key order
        assert log.invalidations("u") == ()
    assert Invalidation.from_json(decision.to_json()) == decision
