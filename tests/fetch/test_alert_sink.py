"""ADR-040: the platform's alert receiver — one JSON line per delivery, a 400 for anything
else, a health answer. Driven through the handler with a fake connection: no socket is ever
opened (the unit-test socket block of ADR-027 §4 stays in force)."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from energy_platform.fetch.alert_sink import AlertSinkHandler, Delivery, parse_delivery

NOW = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)

FIRING = {
    "version": "4",
    "groupKey": '{}:{alertname="EnergyPlatformRestoreDrillFailed"}',
    "status": "firing",
    "receiver": "platform-sink",
    "groupLabels": {"alertname": "EnergyPlatformRestoreDrillFailed"},
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "EnergyPlatformRestoreDrillFailed",
                "severity": "page",
                "job_name": "energy-platform-restore-drill-manual-fail",
            },
            "annotations": {"summary": "a backup could not be restored …"},
            "startsAt": "2026-09-25T09:58:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
        }
    ],
}


class _Connection:
    """What ``StreamRequestHandler`` needs from a socket: ``makefile`` for reading and
    ``sendall`` for writing."""

    def __init__(self, raw: bytes) -> None:
        self._in = io.BytesIO(raw)
        self.out = io.BytesIO()

    def makefile(self, mode: str, *args: Any, **kwargs: Any) -> io.BytesIO:
        return self._in if "r" in mode else self.out

    def sendall(self, data: bytes) -> None:
        self.out.write(data)


def _request(method: str, path: str, body: bytes = b"") -> tuple[str, str]:
    """Run one request through the handler; returns (status line, response body)."""
    head = f"{method} {path} HTTP/1.1\r\nHost: sink\r\nContent-Length: {len(body)}\r\n\r\n"
    conn = _Connection(head.encode() + body)
    log = io.StringIO()
    server = SimpleNamespace(out=log)
    AlertSinkHandler(conn, ("10.0.0.9", 40000), server)  # type: ignore[arg-type]
    response = conn.out.getvalue().decode()
    status, _, rest = response.partition("\r\n")
    _, _, payload = rest.partition("\r\n\r\n")
    return status + "|" + log.getvalue(), payload


def test_parse_delivery_keeps_what_an_operator_needs() -> None:
    d = parse_delivery(json.dumps(FIRING).encode(), now=NOW)
    assert d.status == "firing" and d.receiver == "platform-sink" and len(d.alerts) == 1
    line = json.loads(d.line())
    assert line["received_at"] == "2026-09-25T10:00:00+00:00"
    assert line["alerts"][0]["alertname"] == "EnergyPlatformRestoreDrillFailed"
    assert line["alerts"][0]["labels"]["job_name"] == "energy-platform-restore-drill-manual-fail"
    assert line["alerts"][0]["startsAt"] == "2026-09-25T09:58:00Z"
    assert "\n" not in d.line()  # one line per delivery


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"alerts": "x"}', b"\xff\xfe"])
def test_parse_delivery_refuses_what_is_not_a_webhook_payload(body: bytes) -> None:
    with pytest.raises(ValueError):
        parse_delivery(body, now=NOW)


def test_a_posted_delivery_becomes_one_json_line_and_a_200() -> None:
    status_and_log, payload = _request("POST", "/alerts", json.dumps(FIRING).encode())
    status, _, log = status_and_log.partition("|")
    assert status == "HTTP/1.1 200 OK", status
    assert json.loads(payload) == {"received": 1}
    lines = log.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == "firing"
    resolved = dict(FIRING, status="resolved")
    status_and_log, _ = _request("POST", "/alerts", json.dumps(resolved).encode())
    assert json.loads(status_and_log.partition("|")[2])["status"] == "resolved"


def test_bad_payloads_and_unknown_paths_are_refused_without_a_line() -> None:
    status_and_log, _ = _request("POST", "/alerts", b"garbage")
    status, _, log = status_and_log.partition("|")
    assert status == "HTTP/1.1 400 Bad Request" and log == ""
    status_and_log, _ = _request("POST", "/elsewhere", json.dumps(FIRING).encode())
    assert status_and_log.startswith("HTTP/1.1 404") and status_and_log.endswith("|")
    status_and_log, _ = _request("GET", "/alerts")
    assert status_and_log.startswith("HTTP/1.1 404")


def test_health_answers_ok() -> None:
    status_and_log, payload = _request("GET", "/healthz")
    assert status_and_log == "HTTP/1.1 200 OK|" and payload == "ok\n"


def test_delivery_line_is_deterministic_for_the_same_payload() -> None:
    a = Delivery(NOW, "firing", "platform-sink", tuple(FIRING["alerts"]))  # type: ignore[arg-type]
    b = Delivery(NOW, "firing", "platform-sink", tuple(FIRING["alerts"]))  # type: ignore[arg-type]
    assert a.line() == b.line()
