"""Contracts: the only platform package a target may import (ADR-005, ADR-027).

Two sides of one contract: the manifest (what a source looks like) and the canonical
observation (what the destination looks like), plus the registries both are checked against
and the parser protocol a target may implement. See ``docs/04-contracts.md``.
"""

from energy_platform.contracts.decimals import Separator, Sign, apply_sign, parse_decimal
from energy_platform.contracts.hosts import HOSTS, HostEntry, host
from energy_platform.contracts.intervals import (
    SOURCE_TIMEZONE,
    DeliveryInterval,
    IntervalLabel,
    interval_for_index,
    interval_from_timestamp,
    local_day_intervals,
    parse_duration,
)
from energy_platform.contracts.manifest import (
    SCHEMA_VERSION,
    AdmissionGaps,
    Manifest,
    ManifestSyntaxError,
    Modality,
    ValidationResult,
    ValidationStatus,
    load_manifest,
    validate_manifest,
)
from energy_platform.contracts.observation import (
    EnergyObservation,
    derivation_id,
    observation_identity,
    version_identity,
)
from energy_platform.contracts.parser import (
    Cell,
    DecodedDocument,
    DecodeKind,
    JsonDocument,
    Parser,
    SheetsDocument,
    SourceRecord,
    TabularDocument,
    XmlDocument,
    XmlElement,
)
from energy_platform.contracts.registry import (
    DATASETS,
    DatasetContract,
    MetricSpec,
    SignRule,
    Transport,
    dataset,
)

__all__ = [
    "DATASETS",
    "HOSTS",
    "SCHEMA_VERSION",
    "SOURCE_TIMEZONE",
    "AdmissionGaps",
    "Cell",
    "DatasetContract",
    "DecodeKind",
    "DecodedDocument",
    "DeliveryInterval",
    "EnergyObservation",
    "HostEntry",
    "IntervalLabel",
    "JsonDocument",
    "Manifest",
    "ManifestSyntaxError",
    "MetricSpec",
    "Modality",
    "Parser",
    "Separator",
    "SheetsDocument",
    "Sign",
    "SignRule",
    "SourceRecord",
    "TabularDocument",
    "Transport",
    "ValidationResult",
    "ValidationStatus",
    "XmlDocument",
    "XmlElement",
    "apply_sign",
    "dataset",
    "derivation_id",
    "host",
    "interval_for_index",
    "interval_from_timestamp",
    "load_manifest",
    "local_day_intervals",
    "observation_identity",
    "parse_decimal",
    "parse_duration",
    "validate_manifest",
    "version_identity",
]
