"""The mapping engine: ``SourceRecord`` → ``EnergyObservation`` per the manifest (ADR-005).

Quarantine causes (P2-D6): a time field that does not parse or points outside the local day, a
metric cell that is not a decimal under the declared separator, a ``non_negative`` violation,
an observation the registry rejects, two records claiming one identity with different values.
Everything else is a quality event.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from energy_platform.contracts.decimals import apply_sign, parse_decimal
from energy_platform.contracts.intervals import (
    DeliveryInterval,
    interval_for_index,
    interval_from_timestamp,
)
from energy_platform.contracts.manifest import FieldRef, Manifest
from energy_platform.contracts.observation import EnergyObservation, observation_identity
from energy_platform.contracts.parser import Cell, SourceRecord
from energy_platform.contracts.registry import DatasetContract, dataset
from energy_platform.mapping.quality import QualityEvent, Quarantined
from energy_platform.parse.generic import mapped_source_fields


@dataclass(frozen=True, slots=True)
class MappingContext:
    """Everything the envelope needs that is not in the document (01 §6.1)."""

    target_id: str
    scheduled_for: datetime
    delivery_day: date
    fetched_at: datetime
    raw_ref: str
    payload_sha256: str
    processed_at: datetime
    derivation_id: str


@dataclass(frozen=True, slots=True)
class MappingResult:
    observations: tuple[EnergyObservation, ...]
    events: tuple[QualityEvent, ...]


def map_records(
    manifest: Manifest, records: Iterable[SourceRecord], ctx: MappingContext
) -> MappingResult:
    contract = dataset(manifest.contract.dataset_id)
    if contract is None:
        raise Quarantined(f"dataset {manifest.contract.dataset_id!r} is not registered")
    mapped = set(mapped_source_fields(manifest))
    seen: dict[tuple[object, ...], EnergyObservation] = {}
    events: list[QualityEvent] = []
    unknown: set[str] = set()
    tz = ZoneInfo(manifest.mapping.time.timezone)

    for record in records:
        unknown.update(set(record.fields) - mapped)
        for obs in _map_one(manifest, contract, record, ctx, tz, events):
            key = observation_identity(obs)
            earlier = seen.get(key)
            if earlier is not None and earlier.value != obs.value:
                raise Quarantined(
                    f"{obs.metric} for {obs.delivery_start_utc:%Y-%m-%dT%H:%MZ} appears twice "
                    f"with different values ({earlier.value} vs {obs.value})",
                    record.locator,
                )
            seen.setdefault(key, obs)

    if unknown:
        events.append(
            QualityEvent(
                "unknown_field",
                "warning",
                f"fields not referenced by the mapping: {sorted(unknown)}",
            )
        )
    return MappingResult(observations=tuple(seen.values()), events=tuple(events))


# ------------------------------------------------------------------ one record


def _map_one(
    manifest: Manifest,
    contract: DatasetContract,
    record: SourceRecord,
    ctx: MappingContext,
    tz: ZoneInfo,
    events: list[QualityEvent],
) -> Iterable[EnergyObservation]:
    m = manifest.mapping
    resolution = _text(_ref(m.time.resolution, record, ctx), "resolution", record)
    interval, local_date, period_index = _time(manifest, record, ctx, tz, resolution)
    source_version = (
        None
        if m.source_version is None
        else _text(_ref(m.source_version, record, ctx), "source_version", record)
    )
    published = (
        None
        if m.source_published_at is None
        else _datetime(_ref(m.source_published_at, record, ctx), "source_published_at", record)
    )

    for name, mm in m.metrics.items():
        spec = contract.metric(name)
        if spec is None:  # admission already refused this; defensive
            raise Quarantined(f"metric {name!r} is not registered", record.locator)
        raw = record.fields.get(mm.source)  # absent field → None → NULL, never zero
        try:
            value = apply_sign(parse_decimal(raw, mm.decimal_separator), mm.sign)
        except ValueError as exc:
            raise Quarantined(f"{name}: {exc}", record.locator) from exc
        if value is not None and value < 0:
            if spec.sign == "non_negative":
                raise Quarantined(
                    f"{name}: negative value {value} for a non-negative metric", record.locator
                )
            if spec.sign == "non_negative_expected":
                events.append(
                    QualityEvent(
                        "negative_value",
                        "warning",
                        f"{name} = {value} (registry: >= 0 expected, not enforced)",
                        record.locator,
                        name,
                    )
                )
        try:
            yield EnergyObservation(
                source_id=contract.source_id,
                dataset_id=contract.dataset_id,
                source_transport=manifest.contract.source_transport,
                contract_version=contract.contract_version,
                derivation_id=ctx.derivation_id,
                raw_ref=ctx.raw_ref,
                payload_sha256=ctx.payload_sha256,
                fetched_at=ctx.fetched_at,
                source_published_at=published,
                source_version=source_version,
                processed_at=ctx.processed_at,
                delivery_interval=interval,
                resolution=resolution,
                local_date=local_date,
                period_index=period_index,
                kind="interval",
                dimensions=dict(m.dimensions),
                metric=name,
                value=value,
                unit=mm.unit,
                sign_convention=mm.sign,
            )
        except ValidationError as exc:
            raise Quarantined(f"{name}: {_first_error(exc)}", record.locator) from exc


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    return str(errors[0]["msg"]) if errors else str(exc)


# ------------------------------------------------------------------ time


def _time(
    manifest: Manifest, record: SourceRecord, ctx: MappingContext, tz: ZoneInfo, resolution: str
) -> tuple[DeliveryInterval, date, int | None]:
    t = manifest.mapping.time
    try:
        if t.kind == "period_index":
            local_date = _date(_ref(t.date, record, ctx), record)
            index = _int(_ref(t.index, record, ctx), "period_index", record)
            interval = interval_for_index(local_date, index, resolution, str(tz))
            return interval, local_date, index
        ts = _datetime(_ref(t.timestamp, record, ctx), "timestamp", record)
        if ts is None:
            raise Quarantined("timestamp is empty", record.locator)
        interval = interval_from_timestamp(ts, resolution, t.interval_label)
        return interval, interval.start.astimezone(tz).date(), None
    except (ValueError, IndexError) as exc:
        raise Quarantined(f"time: {exc}", record.locator) from exc


# ------------------------------------------------------------------ field refs and coercions


def _ref(ref: FieldRef | None, record: SourceRecord, ctx: MappingContext) -> Cell | date | datetime:
    if ref is None:
        return None
    if ref.source is not None:
        return record.fields.get(ref.source)
    if ref.constant is not None:
        return ref.constant
    return ctx.delivery_day if ref.context == "delivery_day" else ctx.scheduled_for


def _text(value: Cell | date | datetime, what: str, record: SourceRecord) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise Quarantined(f"{what} is empty", record.locator)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip()


def _int(value: Cell | date | datetime, what: str, record: SourceRecord) -> int:
    if isinstance(value, bool) or value is None:
        raise Quarantined(f"{what} is empty or not a number", record.locator)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise Quarantined(f"{what} is not an integer: {value!r}", record.locator)


def _date(value: Cell | date | datetime, record: SourceRecord) -> date:
    if isinstance(value, datetime):
        return value.astimezone(UTC).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    text = _text(value, "date", record)
    try:
        return date.fromisoformat(text[:10]) if len(text) >= 10 else date.fromisoformat(text)
    except ValueError as exc:
        raise Quarantined(f"date is not ISO 8601: {text!r}", record.locator) from exc


def _datetime(value: Cell | date | datetime, what: str, record: SourceRecord) -> datetime | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise Quarantined(f"{what} is not ISO 8601: {value!r}", record.locator) from exc
    else:
        raise Quarantined(f"{what} is not a timestamp: {value!r}", record.locator)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Quarantined(f"{what} carries no UTC offset: {value!r} (01 §7)", record.locator)
    return parsed
