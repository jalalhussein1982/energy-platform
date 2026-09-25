"""The platform's alert receiver (ADR-040): Alertmanager's webhook, one JSON line per delivery.

``energyctl alert-sink`` runs it as a Deployment on the platform image. It answers
``POST /alerts`` with Alertmanager's webhook payload (``status``, ``groupLabels``, ``alerts``)
by writing one line to its log — the delivery record the alert drill and an operator read —
and ``GET /healthz`` for the readiness probe. It holds no credential, opens no outbound
connection and evaluates nothing: Prometheus evaluates, Alertmanager routes, this receives.
It lives in ``energy_platform.fetch`` because that package owns every socket of the platform
(ADR-027 §3), next to the egress policy gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import IO, Any

PATH = "/alerts"
HEALTH = "/healthz"


@dataclass(frozen=True, slots=True)
class Delivery:
    received_at: datetime
    status: str
    """``firing`` or ``resolved`` — the group's status as Alertmanager sends it."""
    receiver: str
    alerts: tuple[dict[str, Any], ...]

    def line(self) -> str:
        """One JSON line: what fired or resolved, for whom, when."""
        return json.dumps(
            {
                "received_at": self.received_at.isoformat(),
                "status": self.status,
                "receiver": self.receiver,
                "alerts": [
                    {
                        "alertname": a.get("labels", {}).get("alertname"),
                        "status": a.get("status"),
                        "labels": a.get("labels", {}),
                        "summary": a.get("annotations", {}).get("summary"),
                        "startsAt": a.get("startsAt"),
                        "endsAt": a.get("endsAt"),
                    }
                    for a in self.alerts
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )


def parse_delivery(body: bytes, *, now: datetime | None = None) -> Delivery:
    """Alertmanager's webhook payload (``version: "4"``) as a :class:`Delivery`; anything that
    is not a JSON object with a list of alerts is a ``ValueError`` (a 400 for the sender)."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"not a JSON payload: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list):
        raise ValueError("not an Alertmanager webhook payload (no alerts list)")
    alerts = tuple(a for a in payload["alerts"] if isinstance(a, dict))
    status = str(payload.get("status") or "unknown")
    return Delivery(now or datetime.now(UTC), status, str(payload.get("receiver") or ""), alerts)


class AlertSinkHandler(BaseHTTPRequestHandler):
    """``POST /alerts`` → one line on the server's ``out``; ``GET /healthz`` → ``ok``."""

    server_version = "energy-platform-alert-sink"
    sys_version = ""
    protocol_version = "HTTP/1.1"  # Alertmanager keeps its webhook connections alive

    def do_GET(self) -> None:
        if self.path == HEALTH:
            self._answer(200, b"ok\n")
        else:
            self._answer(404, b"not found\n")

    def do_POST(self) -> None:
        if self.path != PATH:
            self._answer(404, b"not found\n")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._answer(400, b"bad Content-Length\n")
            return
        body = self.rfile.read(length) if length > 0 else b""
        try:
            delivery = parse_delivery(body)
        except ValueError as exc:
            self._answer(400, f"{exc}\n".encode())
            return
        out: IO[str] = self.server.out  # type: ignore[attr-defined]
        out.write(delivery.line() + "\n")
        out.flush()
        self._answer(200, json.dumps({"received": len(delivery.alerts)}).encode() + b"\n")

    def log_message(self, format: str, *args: Any) -> None:
        """The delivery lines are the log; the access log would only interleave with them."""

    def _answer(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json" if code == 200 else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AlertSink(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], out: IO[str]) -> None:
        super().__init__(address, AlertSinkHandler)
        self.out = out


def serve(port: int, out: IO[str], host: str = "0.0.0.0") -> None:  # noqa: S104 (a pod listener)
    """Listen until the process is stopped (the container's lifetime)."""
    with AlertSink((host, port), out) as server:
        server.serve_forever()
