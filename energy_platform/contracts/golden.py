"""Golden files: expected canonical rows for one fixture (ADR-020; 05 C-16, C-17).

``targets/<id>/tests/golden/<name>.yaml`` names a fixture directory and either the rows a human
checked against the source document, the quarantine the platform must raise for it, or
``row_count: 0`` for a well-formed document that carries no observation (an empty ``<Result/>``,
01 §9; plan P4-D6). Values are written as quoted strings (``"97.31"``) or ``null``; a YAML float
is refused, the same way a parser may never call ``float()`` on a raw value (01 §9).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

FIXTURE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class GoldenError(ValueError):
    """A golden file that is not a mapping or cannot be loaded."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GoldenRow(_Model):
    """One expected observation, identified the way Silver identifies it (04 §2.3)."""

    delivery_start_utc: AwareDatetime
    resolution: str = Field(pattern=r"^PT\d+[MH]$")
    metric: str = Field(min_length=1)
    value: Decimal | None
    dimensions: Mapping[str, str] | None = None
    source_version: str | None = None
    period_index: int | None = Field(default=None, ge=1)

    @field_validator("value", mode="before")
    @classmethod
    def _no_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("write the value as a quoted string, never a YAML float (01 §9)")
        return v


class Expect(_Model):
    rows: tuple[GoldenRow, ...] = ()
    quarantine: str | None = Field(default=None, min_length=1)
    row_count: int | None = Field(default=None, ge=0)
    quality_events: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _rows_or_quarantine(self) -> Expect:
        if self.quarantine is None and not self.rows and self.row_count != 0:
            raise ValueError(
                "expect.rows needs at least one row, or expect.quarantine a reason, or "
                "expect.row_count: 0 for an empty document"
            )
        if self.quarantine is not None and (self.rows or self.row_count is not None):
            raise ValueError("expect.quarantine excludes rows and row_count")
        return self


class GoldenFile(_Model):
    fixture: str = Field(pattern=FIXTURE_NAME.pattern)
    checked_by: str = Field(min_length=1)
    note: str | None = None
    expect: Expect

    @field_validator("checked_by")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("checked_by must name who checked the values (ADR-020)")
        return v


def load_golden(path: Path) -> GoldenFile:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GoldenError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GoldenError(f"{path}: a golden file is a mapping")
    return GoldenFile.model_validate(data)
