"""Bronze: blob-then-entry order, idempotency, content_changed, 304, hot/cold read, fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from energy_platform.bronze import (
    Bronze,
    BronzeError,
    CaptureEntry,
    FileBlobStore,
    FileCaptureLog,
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
    second = b.capture(
        target_id="t",
        scheduled_for=T0 + timedelta(minutes=15),
        result=result(b"same"),
        transport="soap",
    ).entry
    assert second.content_changed is False
    assert len(blobs) == 1 and len(log.list("t")) == 2
    assert second.raw_ref == log.list("t")[0].raw_ref


def test_304_reuses_the_previous_blob_and_validators() -> None:
    b, blobs, _ = bronze()
    b.capture(target_id="t", scheduled_for=T0, result=result(b"x", etag='"e1"'), transport="xlsx")
    nm = b.capture(
        target_id="t",
        scheduled_for=T0 + timedelta(minutes=15),
        result=result(b"", status=304, not_modified=True),
        transport="xlsx",
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
