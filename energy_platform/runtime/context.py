"""What every verb needs: the manifest, Bronze, the store, a clock and a fetcher factory."""

from __future__ import annotations

import os
import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from energy_platform.bronze import Bronze
from energy_platform.contracts.intervals import SOURCE_TIMEZONE
from energy_platform.contracts.manifest import Manifest
from energy_platform.fetch import Fetcher, SecretResolver
from energy_platform.store import Store

FetcherFactory = Callable[[Manifest], Fetcher]


def default_owner() -> str:
    return f"{platform.node() or 'worker'}:{os.getpid()}"


def utc_now() -> datetime:
    return datetime.now(UTC)


def delivery_day_for(scheduled_for: datetime, tz: str = SOURCE_TIMEZONE) -> date:
    """The delivery day a run is for: the source's civil date of ``scheduled_for`` (01 §7).

    Capture and process derive it the same way, so a capture never has to store it. A
    per-target offset ("hourly for D-1..D-3", 01 §5) is D-5 policy for Phase 4 and will need a
    manifest field by ADR; until then every run is for its own day.
    """
    return scheduled_for.astimezone(ZoneInfo(tz)).date()


@dataclass(frozen=True, slots=True)
class Runtime:
    manifest: Manifest
    bronze: Bronze
    store: Store
    fetcher_factory: FetcherFactory
    clock: Callable[[], datetime] = utc_now
    owner: str = field(default_factory=default_owner)
    lease_ttl: timedelta = timedelta(minutes=5)
    reconcile_window: timedelta = timedelta(hours=48)
    secrets: SecretResolver | None = None

    @property
    def target_id(self) -> str:
        return self.manifest.target_id

    @property
    def timezone(self) -> str:
        return self.manifest.mapping.time.timezone
