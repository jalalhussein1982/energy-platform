"""Generic parsers built from the manifest (ADR-019 five parsers; plan P2-D5).

The platform knows which fields a record must supply — the ``source``-typed refs of the
mapping's time block, ``source_version`` and ``source_published_at`` — so a record is:

* **XML/SOAP**: an element whose attributes (as ``@name``) and leaf children (as their local
  name) together provide every required field; the ČEPS ``information`` echo block and the OTE
  ``Result`` wrapper are not records because they lack the time field;
* **XLSX**: a row below the header row, which is the first row containing every required and
  every mapped header text (whitespace-normalised, exact otherwise); the row set ends at the
  first row whose required cells are blank or change kind (number → text), which is how a
  footer note in the first column is excluded;
* **table / CSV**: rows under the header;
* **JSON**: objects (searched depth-first through lists and dicts) providing the required fields.

Metric fields absent from a record are simply absent (→ NULL downstream). Records carry every
field the unit had; the mapping engine reports unmapped ones as ``unknown_field`` (P2-D6).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

import energy_platform
from energy_platform.contracts.manifest import FieldRef, Manifest
from energy_platform.contracts.parser import (
    Cell,
    DecodedDocument,
    JsonDocument,
    JsonValue,
    Parser,
    SheetsDocument,
    SourceRecord,
    TabularDocument,
    XmlDocument,
    XmlElement,
)


class ParseError(ValueError):
    """The document does not have the shape the manifest describes; it is quarantined."""


def _source(ref: FieldRef | None) -> str | None:
    return None if ref is None else ref.source


def required_source_fields(manifest: Manifest) -> tuple[str, ...]:
    """Fields every record must carry: time refs plus version/publication refs of kind source."""
    t = manifest.mapping.time
    refs = [t.resolution, t.date, t.index, t.timestamp]
    refs += [manifest.mapping.source_version, manifest.mapping.source_published_at]
    return tuple(dict.fromkeys(s for s in (_source(r) for r in refs) if s is not None))


def mapped_source_fields(manifest: Manifest) -> tuple[str, ...]:
    """Every source field the mapping references: required ones plus the metric columns."""
    metrics = tuple(m.source for m in manifest.mapping.metrics.values())
    return tuple(dict.fromkeys(required_source_fields(manifest) + metrics))


def parser_ref(manifest: Manifest) -> str:
    """ADR-023 §1 ``parser_ref`` for the generic parser of this manifest's decode kind, at
    the running implementation (amendment 3: package version plus source digest)."""
    return f"generic:{manifest.contract.decode}@{energy_platform.implementation_version()}"


def generic_parser(manifest: Manifest) -> Parser:
    required = required_source_fields(manifest)
    mapped = mapped_source_fields(manifest)
    decode = manifest.contract.decode
    if decode in {"soap", "xml"}:
        return XmlRecordParser(required)
    if decode == "xlsx":
        return SheetRecordParser(required, mapped)
    if decode in {"csv", "html-table"}:
        return TableRecordParser(required, mapped)
    return JsonRecordParser(required)


def _norm(text: str) -> str:
    return " ".join(text.split())


# ------------------------------------------------------------------ xml / soap


@dataclass(frozen=True, slots=True)
class XmlRecordParser:
    required: tuple[str, ...]

    def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]:
        if not isinstance(doc, XmlDocument):
            raise ParseError(f"XmlRecordParser needs an XmlDocument, got {type(doc).__name__}")
        return tuple(self._walk(doc.root, ""))

    def _fields(self, el: XmlElement) -> dict[str, Cell]:
        fields: dict[str, Cell] = {f"@{k}": v for k, v in el.attrib.items()}
        for child in el.children:
            if not child.children and child.local_name not in fields:
                fields[child.local_name] = child.text
        return fields

    def _walk(self, el: XmlElement, path: str) -> Iterator[SourceRecord]:
        here = f"{path}/{el.local_name}"
        fields = self._fields(el)
        if self.required and all(name in fields for name in self.required):
            yield SourceRecord(fields=fields, locator=here)
            return  # a record's children are its fields, not further records
        for child in el.children:
            yield from self._walk(child, here)


# ------------------------------------------------------------------ xlsx


@dataclass(frozen=True, slots=True)
class SheetRecordParser:
    required: tuple[str, ...]
    mapped: tuple[str, ...]

    def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]:
        if not isinstance(doc, SheetsDocument):
            raise ParseError(f"SheetRecordParser needs a SheetsDocument, got {type(doc).__name__}")
        problems: list[str] = []
        for name, rows in doc.sheets.items():
            try:
                header_index, header = _find_header(rows, self.mapped)
            except ParseError as exc:
                problems.append(f"{name}: {exc}")
                continue
            return tuple(_rows_to_records(rows[header_index + 1 :], header, self.required, name))
        raise ParseError("; ".join(problems) or "workbook has no sheets")


def _find_header(
    rows: tuple[tuple[Cell, ...], ...], mapped: tuple[str, ...]
) -> tuple[int, tuple[str, ...]]:
    wanted = {_norm(m) for m in mapped}
    for i, row in enumerate(rows):
        texts = tuple(_norm(str(c)) if c is not None else "" for c in row)
        if wanted <= set(texts):
            if len({t for t in texts if t}) != len([t for t in texts if t]):
                raise ParseError(f"header row {i + 1} repeats a column name")
            return i, texts
    missing = sorted(wanted - {_norm(str(c)) for r in rows for c in r if c is not None})
    raise ParseError(f"no header row contains the mapped columns; missing {missing}")


def _kind(cell: Cell) -> str:
    return "text" if isinstance(cell, str) else "number"


def _rows_to_records(
    rows: Iterable[tuple[Cell, ...]],
    header: tuple[str, ...],
    required: tuple[str, ...],
    sheet: str,
) -> Iterator[SourceRecord]:
    kinds: dict[str, str] | None = None
    for offset, row in enumerate(rows):
        fields = {h: (row[i] if i < len(row) else None) for i, h in enumerate(header) if h}
        if any(fields.get(name) is None for name in required):
            return  # end of the table: a blank row or a note without the key columns
        if kinds is None:
            kinds = {name: _kind(fields[name]) for name in required}
        elif any(_kind(fields[name]) != kinds[name] for name in required):
            return  # a footer note where a number used to be
        yield SourceRecord(fields=fields, locator=f"{sheet}!row{offset + 1}")


# ------------------------------------------------------------------ csv / html-table


@dataclass(frozen=True, slots=True)
class TableRecordParser:
    required: tuple[str, ...]
    mapped: tuple[str, ...]

    def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]:
        if not isinstance(doc, TabularDocument):
            raise ParseError(f"TableRecordParser needs a TabularDocument, got {type(doc).__name__}")
        header = tuple(_norm(h) for h in doc.header)
        missing = sorted({_norm(m) for m in self.mapped} - set(header))
        if missing:
            raise ParseError(f"table header lacks mapped columns {missing}")
        return tuple(_rows_to_records(doc.rows, header, self.required, doc.kind))


# ------------------------------------------------------------------ json


@dataclass(frozen=True, slots=True)
class JsonRecordParser:
    required: tuple[str, ...]

    def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]:
        if not isinstance(doc, JsonDocument):
            raise ParseError(f"JsonRecordParser needs a JsonDocument, got {type(doc).__name__}")
        return tuple(self._walk(doc.data, "$"))

    def _walk(self, value: JsonValue, path: str) -> Iterator[SourceRecord]:
        if isinstance(value, dict):
            if self.required and all(k in value for k in self.required):
                yield SourceRecord(fields=_scalars(value), locator=path)
                return
            for k, v in value.items():
                yield from self._walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                yield from self._walk(v, f"{path}[{i}]")


def _scalars(obj: Mapping[str, JsonValue]) -> dict[str, Cell]:
    out: dict[str, Cell] = {}
    for k, v in obj.items():
        if v is None or isinstance(v, str | bool | int):
            out[k] = v
        elif isinstance(v, float):
            out[k] = str(v)  # text: the mapping parses it under the declared separator
        # nested lists/objects are not scalar fields of this record
    return out
