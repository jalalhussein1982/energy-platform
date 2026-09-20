"""In-memory manifests for the contracts tests (no file, no network)."""

from __future__ import annotations

import copy
from typing import Any

T1_SOAP_BODY = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:pub="http://www.ote-cr.cz/schema/service/public">'
    "<soapenv:Body><pub:GetImPricePeriodE>"
    "<pub:StartDate>{start_date}</pub:StartDate><pub:EndDate>{end_date}</pub:EndDate>"
    "</pub:GetImPricePeriodE></soapenv:Body></soapenv:Envelope>"
)


def t1_manifest() -> dict[str, Any]:
    """T1 — OTE continuous intraday market, SOAP GetImPricePeriodE (01 §3)."""
    return {
        "schema_version": 1,
        "target_id": "ote_idm_soap",
        "description": "OTE continuous intraday market, SOAP GetImPricePeriodE",
        "license": "OTE Terms of Use; redistribution confirmation pending (01 §10)",
        "terms_url": "https://www.ote-cr.cz/en/documentation/term-of-use",
        "allowed_hosts": ["www.ote-cr.cz"],
        "modality": "soap-xml",
        "cadence": {"cron": "*/15 * * * *", "timezone": "Europe/Prague"},
        "history": {"max_age": "P2Y"},
        "fetch": {
            "soap_xml": {
                "url": "https://www.ote-cr.cz/pw-data/services/PublicDataService",
                "soap_action": "http://www.ote-cr.cz/schema/service/public/GetImPricePeriodE",
                "body_template": T1_SOAP_BODY,
                "params": {
                    "start_date": "{delivery_day:%Y-%m-%d}",
                    "end_date": "{delivery_day:%Y-%m-%d}",
                },
            }
        },
        "contract": {
            "dataset_id": "ote.idm_continuous",
            "source_transport": "soap",
            "decode": "soap",
            "metrics": ["price_vwap", "volume_total"],
        },
        "mapping": {
            "dimensions": {"bidding_zone": "CZ"},
            "time": {
                "kind": "period_index",
                "timezone": "Europe/Prague",
                "date": {"source": "Date"},
                "index": {"source": "PeriodIndex"},
                "resolution": {"source": "PeriodResolution"},
            },
            "metrics": {
                "price_vwap": {"source": "Price", "unit": "EUR/MWh"},
                "volume_total": {"source": "Volume", "unit": "MWh"},
            },
        },
    }


def t3_manifest() -> dict[str, Any]:
    """T3 — ČEPS Load, SOAP (01 §3): timestamp-labelled, version in the identity key."""
    return {
        "schema_version": 1,
        "target_id": "ceps_load_soap",
        "license": "ČEPS web-service terms; review pending (01 §10)",
        "terms_url": "https://www.ceps.cz/en/web-services",
        "allowed_hosts": ["www.ceps.cz"],
        "modality": "soap-xml",
        "cadence": {"cron": "*/15 * * * *"},
        "history": {"max_age": "P1Y"},
        "fetch": {
            "soap_xml": {
                "url": "https://www.ceps.cz/_layouts/CepsData.asmx",
                "soap_action": "https://www.ceps.cz/CepsData/Load",
                "body_template": "<Load>{date_from}{date_to}</Load>",
                "params": {"date_from": "{scheduled_for}", "date_to": "{scheduled_for}"},
            }
        },
        "contract": {
            "dataset_id": "ceps.load",
            "source_transport": "soap",
            "decode": "soap",
            "metrics": ["load_incl_pumping", "load"],
        },
        "mapping": {
            "dimensions": {"area": "CZ", "aggregation_function": "AVG"},
            "time": {
                "kind": "timestamp",
                "timestamp": {"source": "@date"},
                "resolution": {"constant": "PT15M"},
                "interval_label": "start",
            },
            "source_version": {"constant": "RT"},
            "metrics": {
                "load_incl_pumping": {"source": "value1", "unit": "MW"},
                "load": {"source": "value2", "unit": "MW"},
            },
        },
    }


def with_(base: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Deep-copy ``base`` and set ``path`` (dotted) to ``value``; ``value=DELETE`` removes it."""
    data = copy.deepcopy(base)
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        node = node[part]
    if value is DELETE:
        del node[parts[-1]]
    else:
        node[parts[-1]] = value
    return data


DELETE = object()
