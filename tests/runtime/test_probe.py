"""ADR-021 §3 storage-class probe against the fake gateway: the V-6/V-12 behaviours."""

from __future__ import annotations

from datetime import UTC, datetime

from energy_platform.fetch.objectstore import ObjectStoreError
from energy_platform.fetch.offline import Request, Response
from energy_platform.runtime import storage_probe
from tests.bronze.test_s3 import store
from tests.fetch.fake_s3 import FakeS3

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_probe_passes_when_the_gateway_stores_the_class() -> None:
    fake = FakeS3(storage_classes=frozenset({"STANDARD", "COLD"}))
    report = storage_probe(store(fake), "cold", clock=lambda: NOW)
    assert report.ok and report.requested == "COLD" and report.reported == "COLD"
    assert report.key == "probe/20260922T120000Z-COLD" and report.key in fake.objects
    assert fake.objects[report.key].storage_class == "COLD"


def test_probe_fails_on_invalid_argument_with_an_empty_message() -> None:
    """Ceph RGW (V-6, V-12): ``400 InvalidArgument`` and ``<Message></Message>``."""
    fake = FakeS3()
    report = storage_probe(store(fake), "COLD", clock=lambda: NOW)
    assert not report.ok and report.reported is None
    assert "InvalidArgument" in report.message and report.key not in fake.objects


def test_probe_fails_when_head_reports_standard_for_a_cold_request() -> None:
    class Silent(FakeS3):
        def _put(self, key: str, request: Request) -> Response:
            response = super()._put(key, request)
            self.objects[key].storage_class = "STANDARD"  # accepted, silently downgraded
            return response

    fake = Silent(storage_classes=frozenset({"STANDARD", "COLD"}))
    report = storage_probe(store(fake), "COLD", clock=lambda: NOW)
    assert not report.ok and report.reported == "STANDARD"
    assert "stored STANDARD" in report.message


def test_probe_with_standard_passes_but_says_it_proves_nothing() -> None:
    report = storage_probe(store(FakeS3()), "STANDARD", clock=lambda: NOW)
    assert report.ok and "proves nothing" in report.message


def test_client_error_carries_the_code_even_with_an_empty_message() -> None:
    fake = FakeS3()
    try:
        store(fake).put("k", b"x", storage_class="NOPE")
    except ObjectStoreError as exc:
        assert exc.code == "InvalidArgument"
    else:  # pragma: no cover — the assertion above is the test
        raise AssertionError("expected ObjectStoreError")
