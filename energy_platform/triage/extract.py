"""Bounded extraction (ADR-008 mandatory flow: ``UNTRUSTED DATA → bounded extractor/sample``).

The sample is built from what the production decoder and parser produce, never from raw text: a
field inventory and a few example records. For a table the inventory is the decoded header, read
before the manifest-dependent parse (which refuses a header that lacks a mapped column — exactly
the drift triage exists for). Every value is stripped of control and
bidirectional-override characters and truncated; field names that do not look like names are
dropped (a hostile document cannot smuggle a paragraph in as a column header); the serialised
sample has a hard size cap. The sample is data for the model's user message, never part of the
system prompt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from energy_platform.contracts.manifest import Manifest
from energy_platform.contracts.parser import Cell, TabularDocument
from energy_platform.parse import DecodeError, ParseError, generic_parser
from energy_platform.runtime.process import decode_payload

MAX_RECORDS = 3
MAX_VALUE_CHARS = 64
MAX_FIELDS = 64
MAX_SAMPLE_CHARS = 4000
SAFE_NAME = re.compile(r"^[^\W\d][\w .,:()/%@+-]{0,63}$")
"""A source name the pipeline accepts in the sample and in a proposal: an element, attribute or
column-header name (letters of any script first; letters, digits, spaces and ``.,:()/%@+-``)."""

# C0/C1 controls, zero-width and bidirectional formatting characters
_UNSAFE_CHARS = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2060-\u2064\u2066-\u2069]"
)


def clean(value: object, limit: int = MAX_VALUE_CHARS) -> str:
    """One untrusted value as short, printable, single-line text."""
    text = " ".join(_UNSAFE_CHARS.sub(" ", str(value)).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True, slots=True)
class Sample:
    fields: tuple[str, ...]
    records: tuple[Mapping[str, str], ...]
    dropped_fields: int = 0
    parse_error: str | None = None
    truncated: bool = False
    notes: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, object]:
        return {
            "fields": list(self.fields),
            "records": [dict(r) for r in self.records],
            "dropped_fields": self.dropped_fields,
            "parse_error": self.parse_error,
            "truncated": self.truncated,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True, sort_keys=True)


def extract(manifest: Manifest, payload: bytes) -> Sample:
    """The bounded sample of one payload, in the source's own vocabulary."""
    rows_in: list[dict[str, Cell]]
    try:
        doc = decode_payload(manifest, payload)
        if isinstance(doc, TabularDocument):
            rows_in = [dict(zip(doc.header, row, strict=False)) for row in doc.rows]
            names = set(doc.header)
        else:
            rows_in = [dict(r.fields) for r in generic_parser(manifest).parse(doc)]
            names = {n for r in rows_in for n in r}
    except (DecodeError, ParseError) as exc:
        return Sample(fields=(), records=(), parse_error=clean(f"{type(exc).__name__}: {exc}", 200))
    safe = sorted(n for n in names if SAFE_NAME.match(n))[:MAX_FIELDS]
    dropped = len(names) - len(safe)
    rows = [{name: clean(r[name]) for name in safe if name in r} for r in rows_in[:MAX_RECORDS]]
    sample = Sample(fields=tuple(safe), records=tuple(rows), dropped_fields=dropped)
    while len(sample.to_json()) > MAX_SAMPLE_CHARS and sample.records:
        sample = Sample(sample.fields, sample.records[:-1], dropped, truncated=True)
    while len(sample.to_json()) > MAX_SAMPLE_CHARS and sample.fields:
        dropped += 1
        sample = Sample(sample.fields[:-1], (), dropped, truncated=True)
    return sample
