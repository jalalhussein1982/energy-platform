"""The run verbs (ADR-003 rev., ADR-004, ADR-024 §5, ADR-031).

``capture`` fetches on schedule and writes Bronze before touching the ledger; ``reconcile``
rebuilds ledger rows from Bronze; ``process`` claims pending runs under a fence and writes
Silver; ``replay`` never fetches; ``backfill`` fetches only periods with no capture-log entry
and only within ``history.max_age``; ``detect_gaps`` classifies expected instants;
``recapture`` is the ADR-033 correction re-poll; ``smoke`` the ADR-025 upgrade gate;
``storage_probe`` the ADR-021 §3 storage-class probe.
"""

from energy_platform.runtime.backfill import backfill
from energy_platform.runtime.capture import CaptureReport, capture
from energy_platform.runtime.context import Runtime, delivery_day_for
from energy_platform.runtime.cron import CronExpression, cron_instants
from energy_platform.runtime.gaps import Gap, detect_gaps, max_age_cutoff
from energy_platform.runtime.probe import ProbeReport, storage_probe
from energy_platform.runtime.process import ProcessReport, process, process_one
from energy_platform.runtime.recapture import RecaptureReport, last_run_of_day, recapture
from energy_platform.runtime.reconcile import reconcile
from energy_platform.runtime.replay import replay_derivation, replay_range
from energy_platform.runtime.smoke import SmokeReport, fixture_fetcher_factory, smoke

__all__ = [
    "CaptureReport",
    "CronExpression",
    "Gap",
    "ProbeReport",
    "ProcessReport",
    "RecaptureReport",
    "Runtime",
    "SmokeReport",
    "backfill",
    "capture",
    "cron_instants",
    "delivery_day_for",
    "detect_gaps",
    "fixture_fetcher_factory",
    "last_run_of_day",
    "max_age_cutoff",
    "process",
    "process_one",
    "recapture",
    "reconcile",
    "replay_derivation",
    "replay_range",
    "smoke",
    "storage_probe",
]
