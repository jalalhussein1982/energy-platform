"""Generic parsers built from the manifest: records in the source vocabulary (P2-D5)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from energy_platform.contracts.manifest import Manifest, load_manifest
from energy_platform.contracts.parser import (
    JsonDocument,
    JsonValue,
    SourceRecord,
    TabularDocument,
)
from energy_platform.parse.decode import decode
from energy_platform.parse.generic import (
    ParseError,
    generic_parser,
    parser_ref,
    required_source_fields,
)
from tests.synthetic import (
    XLSX_HEADER,
    ceps_load_response,
    ote_empty_result,
    ote_im_price_period_response,
    ote_xlsx,
)

EX = Path("examples/manifests")
T1 = load_manifest(EX / "ote_idm_soap.yaml")
T2 = load_manifest(EX / "ote_idm_xlsx.yaml")
T3 = load_manifest(EX / "ceps_load_soap.yaml")
DAY = date(2026, 9, 17)


def records(manifest: Manifest, payload: bytes) -> list[SourceRecord]:
    return list(generic_parser(manifest).parse(decode(payload, manifest.contract.decode)))


def test_required_fields_are_the_time_and_version_source_refs() -> None:
    assert required_source_fields(T1) == ("PeriodResolution", "Date", "PeriodIndex")
    assert required_source_fields(T2) == ("Period",)  # date comes from context
    assert required_source_fields(T3) == ("@date",)  # source_version is a constant


def test_parser_ref_names_the_generic_parser_and_platform_version() -> None:
    assert parser_ref(T1) == "generic:soap@0.0.1"
    assert parser_ref(T2) == "generic:xlsx@0.0.1"


def test_t1_items_become_records_with_optional_price_and_volume() -> None:
    payload = ote_im_price_period_response(
        DAY, [(1, "170.13", "125.275"), (2, None, "126.025"), (3, "-0.50", None)], emerg=True
    )
    recs = records(T1, payload)
    assert len(recs) == 3
    assert dict(recs[0].fields) == {
        "Date": "2026-09-17",
        "PeriodResolution": "PT15M",
        "PeriodIndex": "1",
        "Emerg": "1",
        "Price": "170.13",
        "Volume": "125.275",
    }
    assert "Price" not in recs[1].fields and recs[1].fields["Volume"] == "126.025"
    assert "Volume" not in recs[2].fields and recs[2].fields["Price"] == "-0.50"
    assert recs[0].locator.endswith("/Result/Item")


def test_t1_full_day_yields_96_records() -> None:
    assert len(records(T1, ote_im_price_period_response(DAY))) == 96


def test_empty_result_is_zero_records_not_an_error() -> None:
    assert records(T1, ote_empty_result()) == []


def test_t3_items_are_records_and_the_information_echo_is_not() -> None:
    recs = records(T3, ceps_load_response(DAY, hours=1))
    assert len(recs) == 4
    assert dict(recs[0].fields) == {
        "@date": "2026-09-17T00:00:00+02:00",
        "@value1": "6382.400",
        "@value2": "6279.867",
    }
    assert all("dateFrom" not in r.fields for r in recs)


def test_t2_header_row_is_found_and_footer_excluded() -> None:
    recs = records(T2, ote_xlsx(DAY))
    assert len(recs) == 96
    first = recs[0].fields
    assert first["Period"] == 1
    assert first["Time interval"] == "00:00-00:15"
    assert first["Traded volume (MWh)"] == Decimal("120.275")
    assert recs[0].locator == "IM!row1"


def test_t2_partial_day_keeps_blank_rows_as_records_with_null_cells() -> None:
    recs = records(T2, ote_xlsx(DAY, filled=8))
    assert len(recs) == 96
    assert recs[7].fields["Average price (EUR/MWh)"] is not None
    assert recs[8].fields["Average price (EUR/MWh)"] is None


def test_t2_dst_days_have_92_and_100_rows() -> None:
    assert len(records(T2, ote_xlsx(date(2026, 3, 29)))) == 92
    assert len(records(T2, ote_xlsx(date(2025, 10, 26)))) == 100
    labels = [r.fields["Time interval"] for r in records(T2, ote_xlsx(date(2025, 10, 26)))]
    assert labels.count("02:00-02:15") == 2  # the repeated label the parser never keys on


def test_t2_changed_unit_header_is_a_parse_error() -> None:
    header = tuple("Traded volume (MW)" if h == "Traded volume (MWh)" else h for h in XLSX_HEADER)
    with pytest.raises(ParseError, match="Traded volume \\(MWh\\)"):
        records(T2, ote_xlsx(DAY, header=header))


def test_t2_duplicate_header_is_a_parse_error() -> None:
    header = (*XLSX_HEADER, "Period")
    with pytest.raises(ParseError, match="repeats"):
        records(T2, ote_xlsx(DAY, header=header))


def test_wrong_document_kind_is_a_parse_error() -> None:
    with pytest.raises(ParseError, match="XmlDocument"):
        generic_parser(T1).parse(TabularDocument(kind="csv", header=("a",), rows=()))


def test_table_parser_over_csv_and_html_table_rows() -> None:
    m = load_manifest(EX / "ote_idm_html_table.yaml")
    header = tuple(x.source for x in m.mapping.metrics.values())
    period = m.mapping.time.index
    assert period is not None and period.source is not None
    doc = TabularDocument(
        kind="html-table",
        header=(period.source, *header),
        rows=(
            ("1", "170,13", "125,275", "60,0", "65,275", "169,00", "171,00", "170,50")[
                : 1 + len(header)
            ],
        ),
    )
    recs = list(generic_parser(m).parse(doc))
    assert len(recs) == 1 and recs[0].fields[period.source] == "1"
    with pytest.raises(ParseError, match="lacks"):
        generic_parser(m).parse(TabularDocument(kind="csv", header=("x",), rows=()))


def test_json_parser_finds_objects_with_the_required_fields() -> None:
    m = load_manifest(EX / "token_api_rest_json.yaml")
    req = required_source_fields(m)
    obj: dict[str, JsonValue] = {k: "2026-09-17T00:00:00+02:00" for k in req}
    obj |= {"value": 1.5, "nested": {"x": 1}}
    doc = JsonDocument(data={"meta": {"n": 1}, "data": [obj, obj]})
    recs = list(generic_parser(m).parse(doc))
    assert len(recs) == 2
    assert recs[0].fields["value"] == "1.5" and "nested" not in recs[0].fields
    assert recs[0].locator == "$.data[0]"
