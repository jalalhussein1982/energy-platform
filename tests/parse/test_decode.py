"""Decoders: shapes, safety (no entity resolution), faults, minimal selector subset."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from energy_platform.contracts.parser import SheetsDocument, TabularDocument, XmlDocument
from energy_platform.parse.decode import (
    DecodeError,
    SoapFault,
    css_to_xpath,
    decode,
    decode_html_table,
)
from tests.synthetic import ceps_load_response, ote_im_price_period_response, ote_xlsx, soap_fault


def test_soap_decodes_to_an_element_view_with_namespaces_stripped_on_lookup() -> None:
    doc = decode(
        ote_im_price_period_response(date(2026, 9, 17), [(1, "170.13", "125.275")]), "soap"
    )
    assert isinstance(doc, XmlDocument) and doc.kind == "soap"
    assert doc.root.local_name == "Envelope"
    item = doc.root.first("Item")
    assert item is not None
    price = item.first("Price")
    assert price is not None and price.text == "170.13"
    assert len(doc.root.find_all("Item")) == 1


def test_soap_fault_over_http_200_is_raised_with_its_reason() -> None:
    with pytest.raises(SoapFault, match="Internal error"):
        decode(soap_fault(), "soap")


def test_soap_root_must_be_an_envelope() -> None:
    with pytest.raises(DecodeError, match="Envelope"):
        decode(b"<Result/>", "soap")


def test_malformed_xml_is_a_decode_error() -> None:
    with pytest.raises(DecodeError, match="well-formed"):
        decode(b"<a><b></a>", "xml")


def test_external_entities_are_not_resolved() -> None:
    payload = (
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>'
        b"<x>&xxe;</x>"
    )
    doc = decode(payload, "xml")
    assert isinstance(doc, XmlDocument)
    assert doc.root.text in (None, "")  # the entity stays unresolved


def test_ceps_attributes_are_exposed_on_the_element() -> None:
    doc = decode(ceps_load_response(date(2026, 9, 17), hours=1), "soap")
    assert isinstance(doc, XmlDocument)
    items = doc.root.find_all("item")
    assert len(items) == 4
    assert items[0].attrib["date"] == "2026-09-17T00:00:00+02:00"
    assert items[0].attrib["value1"] == "6382.400"


def test_xlsx_decodes_numbers_as_decimal_and_keeps_row_positions() -> None:
    doc = decode(ote_xlsx(date(2026, 9, 17)), "xlsx")
    assert isinstance(doc, SheetsDocument)
    rows = doc.sheets["IM"]
    assert rows[5][0] == "Period" and rows[5][2] == "Traded volume (MWh)"
    assert rows[6][0] == 1 and rows[6][1] == "00:00-00:15"
    assert isinstance(rows[6][2], Decimal) and rows[6][2] == Decimal("120.275")
    assert len(rows) == 6 + 96 + 1  # title/blank rows, header, 96 periods, footer


def test_not_an_xlsx() -> None:
    with pytest.raises(DecodeError, match="not an xlsx"):
        decode(b"PK\x03\x04 not really", "xlsx")


def test_csv_header_and_blank_cells() -> None:
    doc = decode(b"\xef\xbb\xbfPeriod,Price\n1,170.13\n2,\n", "csv")
    assert isinstance(doc, TabularDocument)
    assert doc.header == ("Period", "Price")
    assert doc.rows == (("1", "170.13"), ("2", None))


def test_json_decodes_and_rejects_garbage() -> None:
    assert decode(b'{"a": [1, 2]}', "json").kind == "json"
    with pytest.raises(DecodeError, match="not JSON"):
        decode(b"{", "json")


def test_html_table_selector_subset_and_rows() -> None:
    page = b"""<html><body>
    <table class="other"><tr><th>x</th></tr><tr><td>1</td></tr></table>
    <div id="results"><table class="tbl results">
      <tr><th>Period</th><th>Average price (EUR/MWh)</th></tr>
      <tr><td>1</td><td>170,13</td></tr>
      <tr><td>2</td><td></td></tr>
    </table></div></body></html>"""
    doc = decode_html_table(page, "div#results table.results")
    assert doc.header == ("Period", "Average price (EUR/MWh)")
    assert doc.rows == (("1", "170,13"), ("2", None))
    assert css_to_xpath("table.tbl.results") == (
        "//table[contains(concat(' ', normalize-space(@class), ' '), ' tbl ')]"
        "[contains(concat(' ', normalize-space(@class), ' '), ' results ')]"
    )
    with pytest.raises(DecodeError, match="no element matches"):
        decode_html_table(page, "table#missing")
    with pytest.raises(DecodeError, match="unsupported"):
        css_to_xpath("table > tr")
    with pytest.raises(DecodeError, match="table selector"):
        decode(page, "html-table")
