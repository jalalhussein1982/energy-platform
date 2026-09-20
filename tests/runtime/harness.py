"""An offline runtime: memory Bronze, memory store, fixture transport, controllable clock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from energy_platform.bronze import Bronze, MemoryBlobStore, MemoryCaptureLog
from energy_platform.contracts.manifest import Manifest, load_manifest
from energy_platform.fetch import Fetcher, FixtureTransport
from energy_platform.runtime import Runtime
from energy_platform.store import MemoryStore, Store
from tests.synthetic import ceps_load_response, ote_im_price_period_response, ote_xlsx

EX = Path("examples/manifests")
T1 = load_manifest(EX / "ote_idm_soap.yaml")
T2 = load_manifest(EX / "ote_idm_xlsx.yaml")
T3 = load_manifest(EX / "ceps_load_soap.yaml")

# 2026-09-18 00:15 Prague = 22:15 UTC on the 17th; delivery day 2026-09-18
SCHEDULED = datetime(2026, 9, 17, 22, 15, tzinfo=UTC)
DAY = date(2026, 9, 18)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> datetime:
        self.now += delta
        return self.now


def payload_for(manifest: Manifest, day: date = DAY) -> bytes:
    if manifest.target_id == "ote_idm_soap":
        return ote_im_price_period_response(day)
    if manifest.target_id == "ote_idm_xlsx":
        return ote_xlsx(day)
    return ceps_load_response(day)


def fixture_factory(payload: bytes | Callable[[], bytes]) -> Callable[[Manifest], Fetcher]:
    def factory(manifest: Manifest) -> Fetcher:
        body = payload() if callable(payload) else payload
        return Fetcher(
            allowed_hosts=manifest.allowed_hosts,
            allow_insecure=manifest.allow_insecure,
            transport=FixtureTransport(body),
            offline=True,
            sleep=lambda s: None,
        )

    return factory


def runtime(
    manifest: Manifest = T1,
    *,
    payload: bytes | Callable[[], bytes] | None = None,
    store: Store | None = None,
    bronze: Bronze | None = None,
    clock: Clock | None = None,
    owner: str = "w1",
) -> Runtime:
    return Runtime(
        manifest=manifest,
        bronze=bronze or Bronze(MemoryBlobStore(), MemoryCaptureLog()),
        store=store or MemoryStore(),
        fetcher_factory=fixture_factory(payload if payload is not None else payload_for(manifest)),
        clock=clock or Clock(SCHEDULED + timedelta(minutes=1)),
        owner=owner,
        lease_ttl=timedelta(minutes=5),
    )
