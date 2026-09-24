"""Bronze on the fake S3 gateway: key layout, idempotency, hot→cold, entry round trip, listing."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from energy_platform.bronze import (
    Bronze,
    CaptureEntry,
    S3BlobStore,
    S3CaptureLog,
    blob_key,
    sha256_hex,
)
from energy_platform.bronze.s3 import key_instant
from energy_platform.fetch.client import FetchResult
from energy_platform.fetch.objectstore import (
    Credentials,
    ObjectStore,
    ObjectStoreConfig,
    Retention,
)
from tests.fetch.fake_s3 import FakeS3

T0 = datetime(2026, 9, 17, 22, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
CREDS = Credentials("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")


def store(fake: FakeS3, **kw: Any) -> ObjectStore:
    return ObjectStore(
        ObjectStoreConfig(
            endpoint="http://minio.local:9000",
            bucket=fake.bucket,
            allowed_hosts=("minio.local",),
            allow_insecure=True,
            **kw,
        ),
        CREDS,
        transport=fake.transport(),
        clock=lambda: NOW,
        sleep=lambda _: None,
        rng=random.SystemRandom(),
    )


def result(body: bytes) -> FetchResult:
    url = "https://www.ote-cr.cz/pw-data/services/PublicDataService"
    return FetchResult(
        url=url,
        status=200,
        headers={},
        body=body,
        content_type="text/xml",
        fetched_at=T0 + timedelta(minutes=5),
        etag=None,
        last_modified=None,
        not_modified=False,
        hops=(url,),
    )


def entry(target_id: str, scheduled_for: datetime, attempt: int, **kw: Any) -> CaptureEntry:
    sha = sha256_hex(b"x")
    fields: dict[str, Any] = {
        "capture_id": f"{target_id}:{scheduled_for:%Y-%m-%dT%H%M%SZ}:{attempt}",
        "target_id": target_id,
        "scheduled_for": scheduled_for,
        "attempt": attempt,
        "fetched_at": scheduled_for + timedelta(minutes=1),
        "source_url": "https://www.ceps.cz/x",
        "http_status": 200,
        "content_type": "text/xml",
        "payload_sha256": sha,
        "raw_ref": blob_key(sha),
        "size": 1,
        "content_changed": True,
        "source_transport": "soap",
    }
    return CaptureEntry(**{**fields, **kw})


# ------------------------------------------------------------------ blobs


def test_blob_put_uses_the_adr_002_key_and_is_idempotent_by_head() -> None:
    fake = FakeS3()
    blobs = S3BlobStore(store(fake))
    sha = blobs.put(b"<r/>")
    assert sha == sha256_hex(b"<r/>")
    assert fake.calls() == [
        ("HEAD", f"/bronze/bronze/blobs/{sha[:2]}/{sha}"),
        ("PUT", f"/bronze/bronze/blobs/{sha[:2]}/{sha}"),
    ]
    assert blobs.put(b"<r/>") == sha
    assert [m for m, _ in fake.calls()[2:]] == ["HEAD"]  # second put: no PUT on the wire
    assert blobs.exists(sha) and blobs.get(sha) == b"<r/>"
    assert blobs.get("0" * 64) is None and not blobs.exists("0" * 64)


def test_blob_put_carries_retention_headers_when_the_store_has_them() -> None:
    fake = FakeS3()
    blobs = S3BlobStore(store(fake, retention=Retention("COMPLIANCE", 3650)))
    sha = blobs.put(b"locked")
    stored = fake.objects[blob_key(sha)]
    assert stored.lock_mode == "COMPLIANCE" and stored.retain_until == "2036-09-17T10:00:00Z"


# ------------------------------------------------------------------ capture log


def test_entry_round_trips_with_tier_and_is_fetched_by_derived_key() -> None:
    fake = FakeS3()
    log = S3CaptureLog(store(fake))
    e = entry("ote_idm_soap", T0, 2, tier="cold", etag='"abc"')
    log.put(e)
    assert fake.calls() == [
        ("PUT", "/bronze/captures/ote_idm_soap/2026/09/17/2026-09-17T220000Z_2.json")
    ]
    assert fake.objects[e.key].content_type == "application/json"
    fake.requests.clear()
    got = log.get("ote_idm_soap:2026-09-17T220000Z:2")
    assert got == e and got is not None and got.tier == "cold" and got.etag == '"abc"'
    assert fake.calls() == [
        ("GET", "/bronze/captures/ote_idm_soap/2026/09/17/2026-09-17T220000Z_2.json")
    ]
    assert log.get("ote_idm_soap:2026-09-17T220000Z:9") is None
    assert log.get("garbage") is None


def test_entries_for_lists_only_the_instant_prefix() -> None:
    fake = FakeS3()
    log = S3CaptureLog(store(fake))
    for attempt in (2, 1):
        log.put(entry("t", T0, attempt))
    log.put(entry("t", T0 + timedelta(hours=1), 1))
    fake.requests.clear()
    got = log.entries_for("t", T0.astimezone(timezone(timedelta(hours=2))))  # local wall clock
    assert [e.attempt for e in got] == [1, 2]
    listing = fake.calls()[0]
    assert (
        listing[0] == "GET"
        and "prefix=captures%2Ft%2F2026%2F09%2F17%2F2026-09-17T220000Z_" in listing[1]
    )
    assert len(fake.calls()) == 3  # one listing, two GETs


def test_list_filters_the_window_from_keys_and_pages_through_the_listing() -> None:
    fake = FakeS3()
    log = S3CaptureLog(store(fake))
    days = [T0 + timedelta(days=i) for i in range(5)]
    for d in days:
        log.put(entry("t", d, 1))
    log.put(entry("t", days[2], 2))
    log.put(entry("u", days[0], 1))
    fake.objects["captures/t/README"] = fake.objects[entry("t", days[0], 1).key]  # foreign object
    fake.requests.clear()
    window = log.list("t", since=days[1], until=days[3])
    assert [(e.scheduled_for, e.attempt) for e in window] == [
        (days[1], 1),
        (days[2], 1),
        (days[2], 2),
    ]
    gets = [c for c in fake.calls() if c[0] == "GET" and "list-type" not in c[1]]
    assert len(gets) == 3  # only the entries inside the window were fetched
    newest = log.latest("t")
    assert newest is not None and newest.scheduled_for == days[4]
    assert log.latest("nobody") is None
    assert [e.scheduled_for for e in log.list("t")] == [
        days[0],
        days[1],
        days[2],
        days[2],
        days[3],
        days[4],
    ]


def test_list_and_latest_page_through_continuation_tokens() -> None:
    fake = FakeS3(max_keys=2)  # the gateway caps pages: five keys need three listing pages
    log = S3CaptureLog(store(fake))
    for i in range(5):
        log.put(entry("t", T0 + timedelta(hours=i), 1))
    fake.requests.clear()
    assert log.latest("t") == entry("t", T0 + timedelta(hours=4), 1)
    listings = [p for m, p in fake.calls() if m == "GET" and "list-type" in p]
    assert len(listings) == 3 and sum("continuation-token" in p for p in listings) == 2
    assert len(log.list("t")) == 5


def test_key_instant_parses_entry_keys_only() -> None:
    assert key_instant("captures/t/2026/09/17/2026-09-17T220000Z_3.json") == (T0, 3)
    assert key_instant("captures/t/README") is None
    assert key_instant("captures/t/2026/09/17/notastamp_1.json") is None
    assert key_instant("captures/t/2026/09/17/2026-09-17T220000Z.json") is None


# ------------------------------------------------------------------ through the facade


def test_bronze_captures_blob_then_entry_on_s3_and_reads_hot_then_cold() -> None:
    hot, cold = FakeS3(bucket="bronze-hot"), FakeS3(bucket="bronze-cold")
    b = Bronze(S3BlobStore(store(hot)), S3CaptureLog(store(hot)), cold=S3BlobStore(store(cold)))
    out = b.capture(target_id="t", scheduled_for=T0, result=result(b"<r/>"), transport="soap")
    e = out.entry
    put_paths = [p for m, p in hot.calls() if m == "PUT"]
    assert put_paths == [f"/bronze-hot/{e.raw_ref}", f"/bronze-hot/{e.key}"]  # blob before entry
    assert b.read(e.raw_ref).tier == "hot"
    again = b.capture(target_id="t", scheduled_for=T0, result=result(b"other"), transport="soap")
    assert again.created is False and again.entry == e

    # Tiering moved the blob: hot 404 → cold.
    cold.objects[e.raw_ref] = hot.objects.pop(e.raw_ref)
    obj = b.read(e.raw_ref)
    assert (obj.payload, obj.tier) == (b"<r/>", "cold")
    assert cold.calls()[-1] == ("GET", f"/bronze-cold/{e.raw_ref}")
    assert b.verify(e) is True
    cold.objects.pop(e.raw_ref)
    assert b.verify(e) is False


def test_fixture_ingest_on_s3() -> None:
    fake = FakeS3()
    b = Bronze(S3BlobStore(store(fake)), S3CaptureLog(store(fake)))
    e = entry("t", T0, 1)
    b.ingest(e, b"x")
    assert b.log.get(e.capture_id) == e and b.read(e.raw_ref).payload == b"x"


# ------------------------------------------------------------------ create-only entries (DC-06)


def test_entry_create_is_conditional_and_a_412_means_another_writer_won() -> None:
    fake = FakeS3()
    log = S3CaptureLog(store(fake))
    e = entry("t", T0, 1)
    assert log.put_new(e) is True
    put = next(r for r in fake.requests if r.method == "PUT")
    assert put.headers.get("if-none-match") == "*"
    assert log.put_new(entry("t", T0, 1, payload_sha256=sha256_hex(b"other"))) is False
    stored = log.get(e.capture_id)
    assert stored is not None and stored.payload_sha256 == e.payload_sha256  # untouched
    assert [m for m, _ in fake.calls()] == [
        "PUT",
        "GET",
        "PUT",
        "GET",
    ]  # create, read-back, 412, get


def test_entry_create_on_a_gateway_that_ignores_the_header_is_verified_by_read_back() -> None:
    """A store that ignores If-None-Match keeps the last writer: the read-back shows another
    writer's entry, the create reports False and the caller takes the next attempt."""
    fake = FakeS3(honours_if_none_match=False)
    log = S3CaptureLog(store(fake))
    mine = entry("t", T0, 1)
    theirs = entry("t", T0, 1, payload_sha256=sha256_hex(b"theirs"))

    def overwrite(key: str) -> None:  # the other writer lands between our PUT and our GET
        fake.after_put = None
        log.put(theirs)

    fake.after_put = overwrite
    assert log.put_new(mine) is False
    stored = log.get(mine.capture_id)
    assert stored is not None and stored.payload_sha256 == theirs.payload_sha256
