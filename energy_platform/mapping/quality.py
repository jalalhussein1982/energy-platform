"""Quality events and the quarantine exception (01 §9, 01 §3 rule 2, 01 §5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class QualityEvent:
    """Something worth recording that did not stop the document."""

    kind: str
    severity: Severity
    message: str
    locator: str = ""
    metric: str | None = None


class Quarantined(Exception):
    """The whole document is refused with a reason; nothing from it reaches Silver (01 §9)."""

    def __init__(self, reason: str, locator: str = "") -> None:
        super().__init__(f"{reason} at {locator}" if locator else reason)
        self.reason = reason
        self.locator = locator

    def as_event(self) -> QualityEvent:
        return QualityEvent("quarantine", "error", self.reason, self.locator)
