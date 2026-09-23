"""The manifest: source side of the contract (ADR-013, ADR-017, ADR-022, ADR-024, ADR-026, ADR-027).

One YAML document per target, ``targets/<id>/manifest.yaml``. The Pydantic model is the schema;
``schemas/manifest.v1.json`` is exported from it (``make schema``). Validation has two stages:

1. **structural** — ``Manifest.model_validate`` / ``load_manifest``: shape, mandatory fields,
   internal consistency (modality ↔ fetch block ↔ transport ↔ decode), URL hosts ⊆
   ``allowed_hosts``, ``https`` unless ``allow_insecure``, no credential-looking string;
2. **admission** — ``validate_manifest``: every referenced ``dataset_id``, metric and host must
   exist in the platform registries. Anything missing is reported as ``ADMISSION_REQUIRED``
   with the exact gaps (ADR-022 §2), never invented.

Manifests never contain secret values: only ``secretRef {name, key}`` (ADR-017).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from energy_platform.contracts.decimals import Separator, Sign
from energy_platform.contracts.hosts import host as registered_host
from energy_platform.contracts.intervals import IntervalLabel, parse_duration
from energy_platform.contracts.parser import DecodeKind
from energy_platform.contracts.registry import Transport
from energy_platform.contracts.registry import dataset as registered_dataset
from energy_platform.contracts.templates import RUN_NAMES, TemplateError, check_template

SCHEMA_VERSION = 1
Modality = Literal["soap-xml", "dated-file", "html-table", "rest-json", "rest-xml"]

_TARGET_ID = r"^[a-z][a-z0-9_]{2,63}$"
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_CRON = re.compile(r"^(\S+\s+){4}\S+$")
_MAX_AGE = re.compile(r"^(none|P(?=.)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=.)(\d+H)?(\d+M)?)?)$")

# Credential-looking strings a fetch block may never contain (ADR-017). Kept in step with
# scripts/secret_scan.py PATTERNS (a test asserts the shared keys are identical); duplicated
# because platform code never imports scripts/.
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS access key id": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "bearer token": re.compile(r"(?i)\bbearer\s+(?P<value>[a-z0-9._\-]{24,})"),
    "generic assignment": re.compile(
        r"(?i)\b(aws_secret_access_key|secret_key|api[_-]?key|access[_-]?token|password|passwd)"
        r"\s*[:=]\s*['\"]?(?P<value>[A-Za-z0-9/+_\-]{16,})['\"]?"
    ),
    "github token": re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),
    "slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "long opaque token": re.compile(r"(?<![A-Za-z0-9/])[A-Za-z0-9]{40,}(?![A-Za-z0-9/])"),
}


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ------------------------------------------------------------------ fetch blocks (ADR-005)


class SecretRef(_Model):
    """Reference to a platform-resolved secret; the manifest never carries the value."""

    name: str = Field(min_length=1, description="Kubernetes Secret name (env name in `local`)")
    key: str = Field(min_length=1)


_SECRET_KEY = re.compile(r"^[A-Za-z0-9]+$")


def target_secret_name(target_id: str) -> str:
    """The only ``secretRef.name`` a target may use (05 C-63): ``target-<id>``, ``_`` → ``-``.

    Its environment form is ``TARGET_<ID>_<KEY>``; no platform credential starts with
    ``TARGET_`` (``BRONZE_*``, ``POSTGRES_*``, ``ENERGY_PLATFORM_*``), and an alphanumeric key
    makes the last ``_`` the boundary between the target id and the key.
    """
    return "target-" + target_id.replace("_", "-")


class Auth(_Model):
    secretRef: SecretRef  # Kubernetes spelling (ADR-017)
    location: Literal["query", "header"]
    param: str = Field(min_length=1, description="query parameter or header name")


class RateLimit(_Model):
    requests: int = Field(ge=1)
    per: str = Field(description="ISO 8601 duration, e.g. PT1M")

    @field_validator("per")
    @classmethod
    def _duration(cls, v: str) -> str:
        parse_duration(v)
        return v


class Discovery(_Model):
    """Fetch a page and extract the download link (ADR-005 discovery step; T2)."""

    url: str
    link_regex: str = Field(min_length=1)

    @field_validator("link_regex")
    @classmethod
    def _compiles(cls, v: str) -> str:
        re.compile(v)
        return v


class SoapXmlFetch(_Model):
    url: str
    soap_action: str = Field(min_length=1)
    body_template: str = Field(min_length=1, description="SOAP body; `{name}` placeholders")
    params: Mapping[str, str] = Field(default_factory=dict, description="placeholder → expression")
    soap_version: Literal["1.1", "1.2"] = "1.1"


class DatedFileFetch(_Model):
    url_template: str = Field(description="direct URL; `{delivery_day:%d}`-style placeholders")
    file_format: Literal["xlsx", "csv"]
    discovery: Discovery | None = None


class HtmlTableFetch(_Model):
    url: str
    table_selector: str = Field(min_length=1, description="CSS selector of the table")


class RestJsonFetch(_Model):
    url_template: str
    query: Mapping[str, str] = Field(default_factory=dict)
    headers: Mapping[str, str] = Field(default_factory=dict)
    auth: Auth | None = None
    rate_limit: RateLimit | None = None


class RestXmlFetch(_Model):
    url_template: str
    query: Mapping[str, str] = Field(default_factory=dict)
    headers: Mapping[str, str] = Field(default_factory=dict)
    auth: Auth | None = None
    rate_limit: RateLimit | None = None


class FetchBlock(_Model):
    """Exactly one key, named after the modality (plan P1-D3)."""

    soap_xml: SoapXmlFetch | None = None
    dated_file: DatedFileFetch | None = None
    html_table: HtmlTableFetch | None = None
    rest_json: RestJsonFetch | None = None
    rest_xml: RestXmlFetch | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> FetchBlock:
        present = [k for k in _FETCH_KEYS if getattr(self, k) is not None]
        if len(present) != 1:
            raise ValueError(
                f"fetch must contain exactly one of {list(_FETCH_KEYS)}, got {present}"
            )
        return self

    @property
    def key(self) -> str:
        return next(k for k in _FETCH_KEYS if getattr(self, k) is not None)

    def templates(self) -> tuple[tuple[str, str, frozenset[str], bool], ...]:
        """Every string the fetch layer renders: ``(where, template, names, month_index)``."""
        block: Any = getattr(self, self.key)
        found: list[tuple[str, str, frozenset[str], bool]] = []
        if isinstance(block, SoapXmlFetch):
            found += [(f"params.{k}", v, RUN_NAMES, True) for k, v in block.params.items()]
            found.append(("body_template", block.body_template, frozenset(block.params), False))
        elif isinstance(block, DatedFileFetch):
            found.append(("url_template", block.url_template, RUN_NAMES, True))
        elif isinstance(block, RestJsonFetch | RestXmlFetch):
            found.append(("url_template", block.url_template, RUN_NAMES, True))
            found += [(f"query.{k}", v, RUN_NAMES, True) for k, v in block.query.items()]
            found += [(f"headers.{k}", v, RUN_NAMES, True) for k, v in block.headers.items()]
        return tuple(found)

    def urls(self) -> tuple[str, ...]:
        """Every literal URL or URL template in the block, for host and scheme checks."""
        block: Any = getattr(self, self.key)
        found: list[str] = []
        for attr in ("url", "url_template"):
            if hasattr(block, attr):
                found.append(getattr(block, attr))
        if getattr(block, "discovery", None) is not None:
            found.append(block.discovery.url)
        return tuple(found)


_FETCH_KEYS: tuple[str, ...] = ("soap_xml", "dated_file", "html_table", "rest_json", "rest_xml")
_MODALITY_KEY: dict[str, str] = {
    "soap-xml": "soap_xml",
    "dated-file": "dated_file",
    "html-table": "html_table",
    "rest-json": "rest_json",
    "rest-xml": "rest_xml",
}
_MODALITY_TRANSPORTS: dict[str, tuple[Transport, ...]] = {
    "soap-xml": ("soap",),
    "dated-file": ("xlsx", "rest"),  # rest = a plain file over HTTP (csv)
    "html-table": ("html",),
    "rest-json": ("rest",),
    "rest-xml": ("rest",),
}
_MODALITY_DECODES: dict[str, tuple[DecodeKind, ...]] = {
    "soap-xml": ("soap",),
    "dated-file": ("xlsx", "csv"),
    "html-table": ("html-table",),
    "rest-json": ("json",),
    "rest-xml": ("xml",),
}


# ------------------------------------------------------------------ cadence, history, contract


def _five_field_cron(v: str) -> str:
    if not _CRON.match(v.strip()):
        raise ValueError(f"cron must have five fields: {v!r}")
    return v.strip()


class Correction(_Model):
    """Re-poll of the previous ``days`` delivery days on ``cron`` (ADR-033 §3)."""

    cron: str = Field(description="five-field cron expression, evaluated in `cadence.timezone`")
    days: int = Field(ge=1, le=31, description="delivery days D-1 … D-days re-captured per firing")

    @field_validator("cron")
    @classmethod
    def _five_fields(cls, v: str) -> str:
        return _five_field_cron(v)


class Cadence(_Model):
    cron: str = Field(description="five-field cron expression, evaluated in `timezone`")
    timezone: str = "Europe/Prague"
    correction: Correction | None = Field(
        default=None, description="optional correction window re-poll (ADR-033 §3)"
    )

    @field_validator("cron")
    @classmethod
    def _five_fields(cls, v: str) -> str:
        return _five_field_cron(v)

    @field_validator("timezone")
    @classmethod
    def _zone(cls, v: str) -> str:
        return _valid_zone(v)


def _valid_zone(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone {v!r}") from exc
    return v


class History(_Model):
    """How far back the source still serves data; consulted before any backfill (ADR-024 §5)."""

    max_age: str = Field(description="ISO 8601 duration (P2Y, P31D, PT48H) or `none`")

    @field_validator("max_age")
    @classmethod
    def _shape(cls, v: str) -> str:
        if not _MAX_AGE.match(v):
            raise ValueError(f"history.max_age must be an ISO 8601 duration or 'none': {v!r}")
        return v


class Contract(_Model):
    dataset_id: str = Field(min_length=1)
    source_transport: Transport
    decode: DecodeKind
    metrics: tuple[str, ...] = Field(min_length=1)

    @field_validator("metrics")
    @classmethod
    def _unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v):
            raise ValueError("contract.metrics must not repeat a metric")
        return v


# ------------------------------------------------------------------ mapping (ADR-005 normalise)


class FieldRef(_Model):
    """Where a canonical field comes from: a source field, a constant, or the capture context."""

    source: str | None = None
    constant: str | None = None
    context: Literal["delivery_day", "scheduled_for"] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> FieldRef:
        set_ = [k for k in ("source", "constant", "context") if getattr(self, k) is not None]
        if len(set_) != 1:
            raise ValueError(f"exactly one of source/constant/context, got {set_}")
        if self.source is not None:
            _not_positional(self.source)
        return self


class TimeMapping(_Model):
    """01 §7: period index → local interval → UTC, or an offset-aware timestamp plus a label."""

    kind: Literal["period_index", "timestamp"]
    timezone: str = "Europe/Prague"
    resolution: FieldRef
    date: FieldRef | None = None
    index: FieldRef | None = None
    timestamp: FieldRef | None = None
    interval_label: IntervalLabel = "start"

    @field_validator("timezone")
    @classmethod
    def _zone(cls, v: str) -> str:
        return _valid_zone(v)

    @model_validator(mode="after")
    def _shape(self) -> TimeMapping:
        if self.kind == "period_index":
            if self.date is None or self.index is None:
                raise ValueError("time.kind=period_index needs `date` and `index`")
            if self.timestamp is not None:
                raise ValueError("time.kind=period_index does not take `timestamp`")
        else:
            if self.timestamp is None:
                raise ValueError("time.kind=timestamp needs `timestamp`")
            if self.date is not None or self.index is not None:
                raise ValueError("time.kind=timestamp does not take `date`/`index`")
        if self.resolution.constant is not None:
            parse_duration(self.resolution.constant)
        return self


class MetricMapping(_Model):
    source: str = Field(min_length=1, description="source field / column / attribute name")
    unit: str = Field(min_length=1, description="must equal the registry unit; no conversion")
    sign: Sign = "as_published"
    decimal_separator: Separator = "dot"

    @field_validator("source")
    @classmethod
    def _named(cls, v: str) -> str:
        return _not_positional(v)


def _not_positional(source: str) -> str:
    """A column position is not a field name (05 C-04; 04 §2.8 keys on header text)."""
    if source.strip().isdigit():
        raise ValueError(
            f"source {source!r} is a column position; name the header or element "
            "(positional parsing, 05 C-04)"
        )
    return source


class MappingBlock(_Model):
    dimensions: Mapping[str, str] = Field(default_factory=dict)
    time: TimeMapping
    source_version: FieldRef | None = None
    source_published_at: FieldRef | None = None
    metrics: Mapping[str, MetricMapping] = Field(min_length=1)
    ignore_fields: tuple[str, ...] = Field(
        default=(),
        description="source fields the document carries and the mapping deliberately does not "
        "read; they raise no `unknown_field` (ADR-034)",
    )

    @field_validator("ignore_fields")
    @classmethod
    def _named_and_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for name in v:
            if not name.strip():
                raise ValueError("ignore_fields: a name must not be blank")
            _not_positional(name)
        if len(set(v)) != len(v):
            raise ValueError("ignore_fields must not repeat a name")
        return v

    def source_fields(self) -> tuple[str, ...]:
        """Every `source`-typed reference of the block, time fields first (04 §3.6)."""
        refs = [
            self.time.resolution,
            self.time.date,
            self.time.index,
            self.time.timestamp,
            self.source_version,
            self.source_published_at,
        ]
        names = [r.source for r in refs if r is not None and r.source is not None]
        names.extend(m.source for m in self.metrics.values())
        return tuple(dict.fromkeys(names))

    @model_validator(mode="after")
    def _ignored_are_not_mapped(self) -> MappingBlock:
        clash = sorted(set(self.ignore_fields) & set(self.source_fields()))
        if clash:
            raise ValueError(
                f"ignore_fields {clash} are read by the mapping; a field is mapped or ignored, "
                "never both (ADR-034)"
            )
        return self


# ------------------------------------------------------------------ the manifest


class Manifest(_Model):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        title="Manifest",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://energy-platform.invalid/schemas/manifest.v1.json",
        },
    )

    schema_version: Literal[1]
    target_id: str = Field(pattern=_TARGET_ID)
    description: str = ""
    license: str = Field(min_length=1, description="licence / terms under which data is reused")
    terms_url: str
    allowed_hosts: tuple[str, ...] = Field(min_length=1)
    allow_insecure: bool = False
    modality: Modality
    cadence: Cadence
    history: History
    fetch: FetchBlock
    contract: Contract
    mapping: MappingBlock

    @field_validator("terms_url")
    @classmethod
    def _terms_https(cls, v: str) -> str:
        parts = urlsplit(v)
        if parts.scheme != "https" or not parts.netloc:
            raise ValueError(f"terms_url must be an https URL: {v!r}")
        return v

    @field_validator("allowed_hosts")
    @classmethod
    def _hostnames(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for h in v:
            if not _HOSTNAME.match(h):
                raise ValueError(f"allowed_hosts entry is not a lowercase hostname: {h!r}")
        if len(set(v)) != len(v):
            raise ValueError("allowed_hosts must not repeat a host")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> Manifest:
        expected_key = _MODALITY_KEY[self.modality]
        if self.fetch.key != expected_key:
            raise ValueError(
                f"modality {self.modality} requires fetch.{expected_key}, "
                f"found fetch.{self.fetch.key}"
            )
        if self.contract.source_transport not in _MODALITY_TRANSPORTS[self.modality]:
            raise ValueError(
                f"modality {self.modality} allows source_transport "
                f"{_MODALITY_TRANSPORTS[self.modality]}, got {self.contract.source_transport!r}"
            )
        if self.contract.decode not in _MODALITY_DECODES[self.modality]:
            raise ValueError(
                f"modality {self.modality} allows decode {_MODALITY_DECODES[self.modality]}, "
                f"got {self.contract.decode!r}"
            )
        if self.fetch.dated_file is not None:
            if self.fetch.dated_file.file_format != self.contract.decode:
                raise ValueError("fetch.dated_file.file_format must equal contract.decode")
        for url in self.fetch.urls():
            parts = urlsplit(url)
            if parts.scheme == "http" and not self.allow_insecure:
                raise ValueError(
                    f"{url!r} uses http; set allow_insecure: true (and the host registry must "
                    "allow it, ADR-026)"
                )
            if parts.scheme not in {"https", "http"}:
                raise ValueError(f"{url!r} must be https (or http with allow_insecure)")
            if parts.hostname is None or parts.hostname not in self.allowed_hosts:
                raise ValueError(f"{url!r} host is not in allowed_hosts {self.allowed_hosts}")
            if parts.port is not None:
                raise ValueError(f"{url!r} must not set a port; ports come from the host registry")
        secret = _find_secret(self.fetch.model_dump(mode="json"))
        if secret is not None:
            raise ValueError(
                f"fetch block contains a credential-looking string ({secret}); "
                "use secretRef (ADR-017)"
            )
        auth: Auth | None = getattr(getattr(self.fetch, self.fetch.key), "auth", None)
        if auth is not None:
            own = target_secret_name(self.target_id)
            if auth.secretRef.name != own:
                raise ValueError(
                    f"auth.secretRef.name must be {own!r}: a target resolves only its own "
                    f"credentials, never a platform one (got {auth.secretRef.name!r})"
                )
            if not _SECRET_KEY.match(auth.secretRef.key):
                raise ValueError(
                    f"auth.secretRef.key must be alphanumeric (got {auth.secretRef.key!r}): "
                    "it becomes the last part of TARGET_<ID>_<KEY>"
                )
        for where, template, names, month_index in self.fetch.templates():
            try:
                check_template(template, names=names, month_index=month_index)
            except TemplateError as exc:
                raise ValueError(f"fetch.{self.fetch.key}.{where}: {exc}") from exc
        declared = set(self.contract.metrics)
        mapped = set(self.mapping.metrics)
        if declared != mapped:
            raise ValueError(
                f"contract.metrics {sorted(declared)} must equal "
                f"mapping.metrics keys {sorted(mapped)}"
            )
        return self

    def mapping_block(self) -> dict[str, Any]:
        """Canonical JSON form of ``mapping`` — the ``derivation_id`` input (ADR-023 §1)."""
        return self.mapping.model_dump(mode="json", exclude_none=True)


def _find_secret(value: Any, path: str = "fetch") -> str | None:
    if isinstance(value, dict):
        for k, v in value.items():
            hit = _find_secret(v, f"{path}.{k}")
            if hit:
                return hit
    elif isinstance(value, list):
        for i, v in enumerate(value):
            hit = _find_secret(v, f"{path}[{i}]")
            if hit:
                return hit
    elif isinstance(value, str):
        for reason, pat in SECRET_PATTERNS.items():
            if pat.search(value):
                return f"{reason} at {path}"
    return None


# ------------------------------------------------------------------ loading (ADR-017 YAML rules)


class ManifestSyntaxError(ValueError):
    """The file is not the plain YAML subset ADR-017 allows."""


def load_manifest(path: Path) -> Manifest:
    """Read one plain YAML document: no anchors, aliases, merge keys, tags or multiple documents."""
    return parse_manifest(path.read_text(encoding="utf-8"), str(path))


def parse_manifest(text: str, origin: str = "<manifest>") -> Manifest:
    """``load_manifest`` for text already in memory (the triage pipeline checks a patched copy)."""
    for token in yaml.scan(text):
        if isinstance(token, yaml.AnchorToken | yaml.AliasToken):
            raise ManifestSyntaxError(f"{origin}: YAML anchors/aliases are not allowed (ADR-017)")
        if isinstance(token, yaml.TagToken):
            raise ManifestSyntaxError(f"{origin}: YAML tags are not allowed (ADR-017)")
        if isinstance(token, yaml.DocumentStartToken | yaml.DocumentEndToken):
            raise ManifestSyntaxError(f"{origin}: exactly one YAML document, no `---` (ADR-017)")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ManifestSyntaxError(f"{origin}: manifest must be a mapping")
    if "<<" in data:
        raise ManifestSyntaxError(f"{origin}: YAML merge keys are not allowed (ADR-017)")
    return Manifest.model_validate(data)


# ------------------------------------------------------------------ admission (ADR-022 §2)


class AdmissionGaps(_Model):
    """Exactly what a Route B request must add. Empty when the manifest is fully admitted."""

    datasets: tuple[str, ...] = ()
    metrics: tuple[tuple[str, str], ...] = ()
    hosts: tuple[str, ...] = ()
    insecure_hosts: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.datasets or self.metrics or self.hosts or self.insecure_hosts)


ValidationStatus = Literal["OK", "INVALID", "ADMISSION_REQUIRED"]


class ValidationResult(_Model):
    status: ValidationStatus
    errors: tuple[str, ...] = ()
    missing: AdmissionGaps = AdmissionGaps()


def validate_manifest(m: Manifest) -> ValidationResult:
    """Admission check against the registries. Structural validity is assumed (the model did it).

    Status precedence: ``ADMISSION_REQUIRED`` > ``INVALID`` > ``OK``. Gaps and errors are both
    reported so that one round trip shows everything.
    """
    errors: list[str] = []
    missing_datasets: list[str] = []
    missing_metrics: list[tuple[str, str]] = []
    missing_hosts: list[str] = []
    insecure_hosts: list[str] = []

    for h in m.allowed_hosts:
        entry = registered_host(h)
        if entry is None:
            missing_hosts.append(h)
        elif m.allow_insecure and not entry.allow_insecure:
            insecure_hosts.append(h)

    did = m.contract.dataset_id
    contract = registered_dataset(did)
    if contract is None:
        missing_datasets.append(did)
        missing_metrics.extend((did, name) for name in m.contract.metrics)
    else:
        for name in m.contract.metrics:
            spec = contract.metric(name)
            if spec is None:
                missing_metrics.append((did, name))
                continue
            unit = m.mapping.metrics[name].unit
            if unit != spec.unit:
                errors.append(
                    f"metric {name}: unit {unit!r} must be the registry unit {spec.unit!r}"
                )
        expected_dims = contract.manifest_dimensions()
        given = tuple(sorted(m.mapping.dimensions))
        if given != tuple(sorted(expected_dims)):
            errors.append(
                f"mapping.dimensions keys {list(given)} must be exactly {sorted(expected_dims)} "
                f"for {did}"
            )
        else:
            for key, fixed in contract.fixed_dimensions.items():
                if m.mapping.dimensions[key] != fixed:
                    errors.append(
                        f"dimension {key}={m.mapping.dimensions[key]!r} must be {fixed!r}"
                    )
            for key, allowed in contract.allowed_dimension_values.items():
                if m.mapping.dimensions[key] not in allowed:
                    errors.append(f"dimension {key}={m.mapping.dimensions[key]!r} not in {allowed}")
        if contract.version_in_identity and m.mapping.source_version is None:
            errors.append(
                f"{did} carries `version` in its identity key: mapping.source_version needed"
            )
        res = m.mapping.time.resolution.constant
        if res is not None and res not in contract.resolutions:
            errors.append(f"resolution {res!r} is not declared for {did}: {contract.resolutions}")

    gaps = AdmissionGaps(
        datasets=tuple(missing_datasets),
        metrics=tuple(missing_metrics),
        hosts=tuple(missing_hosts),
        insecure_hosts=tuple(insecure_hosts),
    )
    status: ValidationStatus = "ADMISSION_REQUIRED" if gaps else ("INVALID" if errors else "OK")
    return ValidationResult(status=status, errors=tuple(errors), missing=gaps)
