"""The parser contract: the only code a target may contribute (ADR-005, ADR-027 §2).

The platform decodes the raw Bronze bytes according to the manifest's ``contract.decode`` into
one of the ``DecodedDocument`` shapes below **before** a custom parser sees anything. A parser
therefore needs no third-party import; this module itself imports only pure-data standard
library modules so that ``targets/<id>/parser.py`` can import it under the ADR-027 allowlist.

A parser turns a decoded document into ``SourceRecord`` values in the *source's* vocabulary
(``Price``, ``PeriodIndex``, ``@date`` …). Units, timezones, interval conventions and signs are
applied afterwards by the platform from the manifest ``mapping`` block; a parser never does that.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, Protocol, runtime_checkable

Cell = str | Decimal | int | bool | None
"""A decoded scalar: text as the source wrote it, or a native number from a binary format."""

DecodeKind = Literal["xlsx", "xml", "soap", "json", "html-table", "csv"]
"""``contract.decode`` values (ADR-027 §2)."""

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def _frozen(m: Mapping[str, str]) -> Mapping[str, str]:
    return m if isinstance(m, MappingProxyType) else MappingProxyType(dict(m))


@dataclass(frozen=True, slots=True)
class TabularDocument:
    """Rows of cells with a header, from ``csv`` or ``html-table`` decoding."""

    kind: Literal["csv", "html-table"]
    header: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]


@dataclass(frozen=True, slots=True)
class SheetsDocument:
    """Workbook decoded by the platform: sheet name → rows of cells, 0-based, as stored."""

    sheets: Mapping[str, tuple[tuple[Cell, ...], ...]]
    kind: Literal["xlsx"] = "xlsx"


@dataclass(frozen=True, slots=True)
class XmlElement:
    """Read-only element view. ``tag`` keeps the ``{namespace}local`` form the decoder produced."""

    tag: str
    attrib: Mapping[str, str]
    text: str | None
    children: tuple[XmlElement, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attrib", _frozen(self.attrib))

    @property
    def local_name(self) -> str:
        return self.tag.rsplit("}", 1)[-1]

    def find_all(self, local_name: str) -> tuple[XmlElement, ...]:
        """Descendants (depth-first, document order) whose local name matches; not self."""
        found: list[XmlElement] = []
        for child in self.children:
            if child.local_name == local_name:
                found.append(child)
            found.extend(child.find_all(local_name))
        return tuple(found)

    def first(self, local_name: str) -> XmlElement | None:
        for child in self.children:
            if child.local_name == local_name:
                return child
            nested = child.first(local_name)
            if nested is not None:
                return nested
        return None


@dataclass(frozen=True, slots=True)
class XmlDocument:
    """``xml`` or ``soap`` decoding; for ``soap`` the root is the SOAP ``Envelope``."""

    kind: Literal["xml", "soap"]
    root: XmlElement


@dataclass(frozen=True, slots=True)
class JsonDocument:
    data: JsonValue
    kind: Literal["json"] = "json"


DecodedDocument = TabularDocument | SheetsDocument | XmlDocument | JsonDocument


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One source-shaped record. ``locator`` names where it came from for quarantine messages."""

    fields: Mapping[str, Cell]
    locator: str = field(default="")

    def __post_init__(self) -> None:
        if not isinstance(self.fields, MappingProxyType):
            object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def __hash__(self) -> int:
        return hash((tuple(sorted(self.fields.items(), key=lambda kv: kv[0])), self.locator))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SourceRecord):
            return NotImplemented
        return dict(self.fields) == dict(other.fields) and self.locator == other.locator


@runtime_checkable
class Parser(Protocol):
    """Exactly one class in ``targets/<id>/parser.py`` implements this (ADR-017)."""

    def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]: ...
