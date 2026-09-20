"""Parser protocol and the decoded-document shapes a target parser receives (ADR-027 §2)."""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from energy_platform.contracts.parser import (
    DecodedDocument,
    JsonDocument,
    Parser,
    SheetsDocument,
    SourceRecord,
    TabularDocument,
    XmlDocument,
    XmlElement,
)

PARSER_MODULE = Path("energy_platform/contracts/parser.py")


class _ToyParser:
    def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]:
        assert isinstance(doc, XmlDocument)
        for i, item in enumerate(doc.root.find_all("Item")):
            date_el = item.first("Date")
            price_el = item.first("Price")
            yield SourceRecord(
                fields={
                    "Date": date_el.text if date_el is not None else None,
                    "Price": price_el.text if price_el is not None else None,
                },
                locator=f"Item[{i}]",
            )


def _soap_doc() -> XmlDocument:
    ns = "{http://www.ote-cr.cz/schema/service/public}"
    item1 = XmlElement(
        tag=f"{ns}Item",
        attrib={},
        text=None,
        children=(
            XmlElement(f"{ns}Date", {}, "2026-09-17", ()),
            XmlElement(f"{ns}Price", {}, "170.13", ()),
        ),
    )
    item2 = XmlElement(f"{ns}Item", {}, None, (XmlElement(f"{ns}Date", {}, "2026-09-17", ()),))
    result = XmlElement(f"{ns}Result", {}, None, (item1, item2))
    return XmlDocument(kind="soap", root=XmlElement("Envelope", {}, None, (result,)))


def test_toy_parser_satisfies_protocol() -> None:
    parser: Parser = _ToyParser()
    assert isinstance(parser, Parser)
    records = list(parser.parse(_soap_doc()))
    assert records == [
        SourceRecord(fields={"Date": "2026-09-17", "Price": "170.13"}, locator="Item[0]"),
        SourceRecord(fields={"Date": "2026-09-17", "Price": None}, locator="Item[1]"),
    ]


def test_object_without_parse_is_not_a_parser() -> None:
    assert not isinstance(object(), Parser)


def test_xml_find_all_ignores_namespace_and_is_depth_first() -> None:
    root = _soap_doc().root
    assert [e.local_name for e in root.find_all("Item")] == ["Item", "Item"]
    assert root.first("Price") is not None
    assert root.first("Missing") is None
    assert root.find_all("Envelope") == ()  # descendants only, not self


def test_xml_element_attributes_are_read_only() -> None:
    e = XmlElement("item", {"date": "2026-09-17T00:00:00+02:00"}, None, ())
    with pytest.raises(TypeError):
        e.attrib["date"] = "x"  # type: ignore[index]


def test_source_record_is_frozen_and_hashable() -> None:
    r = SourceRecord(fields={"a": Decimal("1.5")}, locator="row 7")
    assert hash(r)
    with pytest.raises(TypeError):
        r.fields["a"] = None  # type: ignore[index]


def test_tabular_and_sheets_shapes() -> None:
    t = TabularDocument(kind="csv", header=("Period", "Price"), rows=(("1", "170,13"),))
    assert t.rows[0][1] == "170,13"
    s = SheetsDocument(sheets={"IM_15MIN": ((None, "Period"), (1, Decimal("170.13")))})
    assert s.kind == "xlsx"
    assert s.sheets["IM_15MIN"][1][1] == Decimal("170.13")
    j = JsonDocument(data={"2026-09-17T00:00Z": [1, 2.5, None]})
    assert j.kind == "json"


def test_parser_module_imports_only_what_a_target_parser_may() -> None:
    """A target's parser.py imports this module; it must not drag in anything else (ADR-027)."""
    allowed = {
        "__future__",
        "decimal",
        "datetime",
        "zoneinfo",
        "re",
        "typing",
        "dataclasses",
        "collections",
        "collections.abc",
        "enum",
        "itertools",
        "functools",
        "math",
        "fractions",
        "types",
    }
    tree = ast.parse(PARSER_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed, node.module


def _records() -> Iterator[SourceRecord]:
    yield SourceRecord(fields={}, locator="")


def test_iterable_return_is_enough() -> None:
    class Gen:
        def parse(self, doc: DecodedDocument) -> Iterable[SourceRecord]:
            return _records()

    assert isinstance(Gen(), Parser)
