"""The intended instant of a scheduled capture (ADR-031 amendment 1; review 3 R2).

A run's identity is a firing instant of the manifest's cadence — the instant the gap detector
expects, the instant Bronze entries and ledger rows are keyed by. The wall clock at which the
pod started is not that instant: a CronJob's pod starts seconds after its tick (and up to
``startingDeadlineSeconds`` after it), so a capture keyed by ``now()`` never matched its tick,
every good capture read as a phantom ``missing_capture`` and the backfill fetched the same day
again (2026-09-25, review 3 R2: every scheduled capture on the demo since 2026-09-23).

Two sources, in order:

1. **The controller's own tick.** A Job created by a CronJob is named
   ``<cronjob>-<minutes since the epoch>`` of its *scheduled* time (kube-controller-manager
   ``getJobName``; the demo's ``energy-platform-capture-ceps-load-29838195`` is
   2026-09-24T23:15:00Z). The chart passes that name to the capture container by the downward
   API (``ENERGY_PLATFORM_JOB_NAME``). The suffix is used when it decodes to a firing instant of
   the cadence within the last day; a name without one (``restore-drill-manual-3``, a
   ``kubectl create job`` by hand) is ignored.
2. **The newest firing instant at or before now** — the fallback for a manual Job and a laptop
   run. It never invents an older instant: a tick that no capture served stays missing, and the
   gap detector still reports it (``tests/runtime/test_review3.py``).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from energy_platform.contracts.manifest import Manifest
from energy_platform.runtime.cron import CronExpression, cron_instants

JOB_NAME_ENV = "ENERGY_PLATFORM_JOB_NAME"
"""Set by the chart from the pod label ``batch.kubernetes.io/job-name`` (downward API)."""

_JOB_SUFFIX = re.compile(r"-(?P<minutes>\d{6,9})$")
"""Minutes since the epoch: 6 digits reach 1971, 9 digits the year 3871."""

_ONE_DAY = timedelta(days=1)


def instant_from_job_name(name: str | None) -> datetime | None:
    """The scheduled instant a CronJob-created Job carries in its name, or ``None``."""
    if not name:
        return None
    m = _JOB_SUFFIX.search(name.strip())
    if m is None:
        return None
    return datetime.fromtimestamp(int(m.group("minutes")) * 60, tz=UTC)


def latest_instant(
    expression: str, timezone: str, now: datetime, *, window: timedelta = timedelta(days=62)
) -> datetime | None:
    """The newest firing instant of ``expression`` (evaluated in ``timezone``) at or before
    ``now``, searched one day at a time back through ``window``; ``None`` when the cadence has
    no instant in the window (a cadence rarer than two months)."""
    end = now.astimezone(UTC).replace(second=0, microsecond=0)
    # cron_instants yields start < t <= end: include the minute of ``now`` itself
    step = _ONE_DAY
    searched = timedelta()
    while searched < window:
        start = end - step
        found = list(cron_instants(expression, timezone, start, end))
        if found:
            return found[-1]
        end = start
        searched += step
    return None


def is_firing_instant(expression: str, timezone: str, instant: datetime) -> bool:
    if instant.second or instant.microsecond:
        return False
    return CronExpression.parse(expression).matches(instant.astimezone(ZoneInfo(timezone)))


def intended_instant(manifest: Manifest, now: datetime, job_name: str | None = None) -> datetime:
    """The run this capture is for: the controller's tick when the Job name carries one that
    is a firing instant of the cadence within the last day, else the newest firing instant at
    or before ``now``, else ``now`` floored to the minute (a cadence rarer than the search
    window; the ledger still gets a minute-exact instant)."""
    cadence = manifest.cadence
    tick = instant_from_job_name(job_name)
    if tick is not None and now - _ONE_DAY <= tick <= now:
        if is_firing_instant(cadence.cron, cadence.timezone, tick):
            return tick
    latest = latest_instant(cadence.cron, cadence.timezone, now)
    if latest is not None:
        return latest
    return now.astimezone(UTC).replace(second=0, microsecond=0)
