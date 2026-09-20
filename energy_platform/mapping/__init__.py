"""Normalise: execute the manifest ``mapping`` block (ADR-005; 04 §2.7, §2.8, §3.6).

Source records in the source's vocabulary become ``EnergyObservation`` rows: intervals from
period indices or offset-aware timestamps, decimals under the declared separator, sign rules
from the registry, and the quarantine rules of 01 §9. Quality events (01 §3 reconciliation,
01 §5 completeness, negative values where only "expected ≥ 0") are data, never exceptions.
"""

from energy_platform.mapping.completeness import partition_status
from energy_platform.mapping.engine import MappingContext, MappingResult, map_records
from energy_platform.mapping.quality import QualityEvent, Quarantined, Severity
from energy_platform.mapping.reconcile import TOLERANCES, reconcile_transports

__all__ = [
    "TOLERANCES",
    "MappingContext",
    "MappingResult",
    "QualityEvent",
    "Quarantined",
    "Severity",
    "map_records",
    "partition_status",
    "reconcile_transports",
]
