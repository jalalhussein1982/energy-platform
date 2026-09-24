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
from typing import Any

from energy_platform.contracts.manifest import Manifest
from energy_platform.contracts.parser import (
    Cell,
    DecodedDocument,
    JsonDocument,
    JsonValue,
    TabularDocument,
    XmlDocument,
    XmlElement,
)
from energy_platform.parse import DecodeError, ParseError, generic_parser
from energy_platform.runtime.process import decode_payload

MAX_RECORDS = 3
MAX_VALUE_CHARS = 64
MAX_FIELDS = 64
MAX_SAMPLE_CHARS = 4000
SAFE_NAME = re.compile(r"^@?[^\W\d][\w .,:()/%@+-]{0,63}$")
"""A source name the pipeline accepts in the sample and in a proposal: an element, attribute or
column-header name (letters of any script first, or the platform's ``@attribute`` form; letters,
digits, spaces and ``.,:()/%@+-``). Review 2 AE-01: ``@date`` and ``@value1`` are real T3
sources and used to be dropped as unsafe, which hid a renamed attribute."""

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


def _record_fields(el: XmlElement) -> dict[str, Cell]:
    """The generic XML parser's view of one element: attributes as ``@name``, leaf children."""
    fields: dict[str, Cell] = {f"@{k}": v for k, v in el.attrib.items()}
    for child in el.children:
        if not child.children and child.local_name not in fields:
            fields[child.local_name] = child.text
    return fields


def _largest_sibling_group(root: XmlElement) -> list[XmlElement]:
    """The most numerous run of same-named siblings anywhere in the tree: what a record set
    looks like whatever the elements are called (review 2 AE-01: a renamed required field made
    the generic parser recognise no record at all, and the inventory vanished with it)."""
    best: list[XmlElement] = []

    def walk(el: XmlElement) -> None:
        nonlocal best
        groups: dict[str, list[XmlElement]] = {}
        for child in el.children:
            groups.setdefault(child.local_name, []).append(child)
        for members in groups.values():
            if len(members) > len(best):
                best = members
        for child in el.children:
            walk(child)

    walk(root)
    return best


def _largest_object_list(value: JsonValue) -> list[dict[str, Any]]:
    best: list[dict[str, Any]] = []

    def walk(node: JsonValue) -> None:
        nonlocal best
        if isinstance(node, list):
            objects: list[dict[str, Any]] = [n for n in node if isinstance(n, dict)]
            if len(objects) > len(best):
                best = objects
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            for n in node.values():
                walk(n)

    walk(value)
    return best


def inventory(manifest: Manifest, doc: DecodedDocument) -> list[dict[str, Cell]]:
    """Record-shaped rows of the decoded document, **independently of the mapping**: the
    generic parser's records when it recognises any; otherwise the document's own record set —
    the largest run of same-named XML siblings, the largest JSON list of objects — so a renamed
    required field shows up as a missing source and an unknown one, not as an empty document.
    A table's header is its inventory before any parse; a sheet's header detection remains the
    parser's (it needs the mapped column texts to find the header row)."""
    if isinstance(doc, TabularDocument):
        return [dict(zip(doc.header, row, strict=False)) for row in doc.rows]
    rows = [dict(r.fields) for r in generic_parser(manifest).parse(doc)]
    if rows:
        return rows
    if isinstance(doc, XmlDocument):
        return [_record_fields(el) for el in _largest_sibling_group(doc.root)]
    if isinstance(doc, JsonDocument):
        return [
            {str(k): (v if isinstance(v, str | int) or v is None else str(v)) for k, v in o.items()}
            for o in _largest_object_list(doc.data)
        ]
    return []


def extract(manifest: Manifest, payload: bytes) -> Sample:
    """The bounded sample of one payload, in the source's own vocabulary."""
    rows_in: list[dict[str, Cell]]
    try:
        doc = decode_payload(manifest, payload)
        rows_in = inventory(manifest, doc)
        names = (
            set(doc.header) if isinstance(doc, TabularDocument) else {n for r in rows_in for n in r}
        )
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
