"""Dataset registry: the typed contracts a target may reference (ADR-022, 01 §6.3 and §9).

A target *registers* a contract; it cannot invent dimensions, units or metric names. Adding or
changing an entry here is a Route B platform PR under CODEOWNERS. Candidates from 01 §4/§6.3 are
deliberately absent: admission is a licensing and semantics decision per source.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

SignRule = Literal["negative_allowed", "non_negative", "non_negative_expected"]
"""``non_negative`` is enforced at mapping time; ``non_negative_expected`` only raises a quality
event (01 §9: ČEPS load "≥ 0 expected, not enforced")."""

Transport = Literal["soap", "xlsx", "html", "rest"]

TIME_DIMENSIONS: tuple[str, str] = ("delivery_start_utc", "resolution")
"""Identity dimensions bound to the time fields, never to ``mapping.dimensions``."""

VERSION_DIMENSION = "version"
"""Identity dimension bound to the envelope ``source_version`` (plan P1-D2)."""


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    unit: str
    currency: str | None
    sign: SignRule
    null_meaning: str
    owner_transport: Transport | None = None
    """Which transport is the system of record when several deliver the metric (01 §3 rules)."""


Partition = Literal["day", "hour"]


@dataclass(frozen=True, slots=True)
class DatasetContract:
    dataset_id: str
    source_id: str
    contract_version: str
    identity_key: tuple[str, ...]
    fixed_dimensions: Mapping[str, str]
    metrics: Mapping[str, MetricSpec]
    resolutions: tuple[str, ...]
    allowed_dimension_values: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    """Constrained free dimensions (e.g. ``aggregation_function`` ∈ {AVG}); the manifest supplies
    one constant value per key."""
    partition: Partition = "day"
    """Freshness partition (01 §5, ADR-037): a delivery day, or a delivery hour (ČEPS load)."""

    def metric(self, name: str) -> MetricSpec | None:
        return self.metrics.get(name)

    def manifest_dimensions(self) -> tuple[str, ...]:
        """Identity dimensions the manifest must supply as constants, in identity-key order."""
        return tuple(
            d for d in self.identity_key if d not in TIME_DIMENSIONS and d != VERSION_DIMENSION
        )

    @property
    def version_in_identity(self) -> bool:
        return VERSION_DIMENSION in self.identity_key


def _metrics(*specs: MetricSpec) -> Mapping[str, MetricSpec]:
    return MappingProxyType({s.name: s for s in specs})


_IDM_PRICE_NULL = "no trade in period, or not yet published"
_IDM_VOLUME_NULL = "not yet published"

_OTE_IDM_CONTINUOUS = DatasetContract(
    dataset_id="ote.idm_continuous",
    source_id="ote",
    contract_version="1.0.0",
    identity_key=("bidding_zone", "delivery_start_utc", "resolution"),
    fixed_dimensions=MappingProxyType({"bidding_zone": "CZ"}),
    resolutions=("PT15M", "PT60M"),
    metrics=_metrics(
        # T1 (SOAP GetImPricePeriodE) is the system of record for these two (01 §3 rule 2)
        MetricSpec("price_vwap", "EUR/MWh", "EUR", "negative_allowed", _IDM_PRICE_NULL, "soap"),
        MetricSpec("volume_total", "MWh", None, "non_negative", _IDM_VOLUME_NULL, "soap"),
        # T2 (daily XLSX) is the only source of these five (01 §3 rule 3)
        MetricSpec("volume_buy", "MWh", None, "non_negative", _IDM_VOLUME_NULL, "xlsx"),
        MetricSpec("volume_sell", "MWh", None, "non_negative", _IDM_VOLUME_NULL, "xlsx"),
        MetricSpec("price_min", "EUR/MWh", "EUR", "negative_allowed", _IDM_PRICE_NULL, "xlsx"),
        MetricSpec("price_max", "EUR/MWh", "EUR", "negative_allowed", _IDM_PRICE_NULL, "xlsx"),
        MetricSpec("price_last", "EUR/MWh", "EUR", "negative_allowed", _IDM_PRICE_NULL, "xlsx"),
    ),
)

_OTE_DAM = DatasetContract(
    dataset_id="ote.dam",
    source_id="ote",
    contract_version="1.0.0",
    identity_key=("bidding_zone", "delivery_start_utc", "resolution"),
    fixed_dimensions=MappingProxyType({"bidding_zone": "CZ"}),
    resolutions=("PT15M", "PT60M"),
    metrics=_metrics(
        MetricSpec("price", "EUR/MWh", "EUR", "negative_allowed", "no result", "soap"),
        MetricSpec("price_hourly", "EUR/MWh", "EUR", "negative_allowed", "no result", "soap"),
        MetricSpec("volume_total", "MWh", None, "non_negative", "no result", "soap"),
        # dimensionless flag: 1 when a state of emergency was declared (01 §3 E1)
        MetricSpec("emergency_state", "1", None, "non_negative", "no result", "soap"),
    ),
)

_CEPS_LOAD = DatasetContract(
    dataset_id="ceps.load",
    source_id="ceps",
    contract_version="1.0.0",
    identity_key=("area", "delivery_start_utc", "resolution", "aggregation_function", "version"),
    fixed_dimensions=MappingProxyType({"area": "CZ"}),
    # only AVG is live-verified (01 §3 T3); other functions are [UNVERIFIED] and not admitted
    allowed_dimension_values=MappingProxyType({"aggregation_function": ("AVG",)}),
    resolutions=("PT15M",),
    partition="hour",
    metrics=_metrics(
        MetricSpec(
            "load_incl_pumping", "MW", None, "non_negative_expected", "missing sample", "soap"
        ),
        MetricSpec("load", "MW", None, "non_negative_expected", "missing sample", "soap"),
    ),
)

DATASETS: Mapping[str, DatasetContract] = MappingProxyType(
    {c.dataset_id: c for c in (_OTE_IDM_CONTINUOUS, _OTE_DAM, _CEPS_LOAD)}
)


def dataset(dataset_id: str) -> DatasetContract | None:
    """Exact lookup; ``None`` means "not admitted" (Route B, ADR-022), never "invent one"."""
    return DATASETS.get(dataset_id)
