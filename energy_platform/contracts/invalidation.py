"""A durable invalidation decision (ADR-038; review 2 DC-07).

An invalidation says: *the output of capture ``capture_id`` (for one derivation, or for every
derivation when ``derivation_id`` is ``None``) is known to be wrong and must not be current,
replayed or restored*. It is a Bronze object (``invalidations/<target>/…json``, immutable,
replicated with the bucket) mirrored into the ``invalidations`` table by ``reconcile``, so a
rebuild from Bronze alone honours it. The raw capture is never touched: evidence stays.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

_STAMP = "%Y-%m-%dT%H%M%SZ"


class Invalidation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_id: str = Field(min_length=1)
    capture_id: str = Field(min_length=1, description="`<target>:<stamp>:<attempt>`")
    derivation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    """``None``: every derivation's output of this capture is invalid."""
    reason: str = Field(min_length=1, max_length=2000)
    recorded_by: str = Field(min_length=1, max_length=200)
    recorded_at: AwareDatetime

    @field_validator("recorded_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC)

    @field_validator("capture_id")
    @classmethod
    def _shape(cls, v: str) -> str:
        parts = v.rsplit(":", 2)
        if len(parts) != 3 or not parts[2].isdigit():
            raise ValueError(f"capture id {v!r} is not <target>:<stamp>:<attempt>")
        return v

    @property
    def key(self) -> str:
        return invalidation_key(self.target_id, self.capture_id, self.derivation_id)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> Invalidation:
        return cls.model_validate(json.loads(text))


def invalidation_key(target_id: str, capture_id: str, derivation_id: str | None) -> str:
    """``invalidations/<target_id>/<stamp>_<attempt>[.<derivation>].json`` — one object per
    decision, beside the capture log's prefix (ADR-002 layout)."""
    _, stamp, attempt = capture_id.rsplit(":", 2)
    scope = "" if derivation_id is None else f".{derivation_id}"
    return f"invalidations/{target_id}/{stamp}_{attempt}{scope}.json"
