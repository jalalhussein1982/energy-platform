"""The LLM seam of the drift-triage pipeline (ADR-009, D-10: "pipeline built, LLM step stubbed").

``LLMBackend`` is the only contract: text in (a constant system prompt and a JSON user message
whose ``sample`` is untrusted data), text out (JSON the pipeline then parses and constrains). The
answer is never trusted: ``energy_platform.triage.pipeline`` refuses anything outside the allowed
operations, so a backend — stub, local model or compromised endpoint — can at most propose a
manifest-only change that a human reviews.

The OpenAI-compatible HTTP backend ADR-009 names is deliberately not built here: outbound HTTP
lives only in ``energy_platform.fetch`` (ADR-027), and its endpoint would be one more entry in the
host registry (ADR-026). Until then the platform runs with the deterministic stub, and an absent
or failing backend changes nothing but the triage result (ADR-009 hard requirement).
"""

from __future__ import annotations

import difflib
import json
from typing import Protocol


class LLMUnavailable(RuntimeError):
    """No backend, or the backend failed: triage returns ``no_proposal``, nothing else changes."""


class LLMBackend(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str:
        """Return the model's reply to one exchange; raise ``LLMUnavailable`` if it cannot."""
        ...


class UnavailableBackend:
    """The ADR-009 failure mode made explicit: there is no model to ask."""

    name = "unavailable"

    def complete(self, system: str, user: str) -> str:
        raise LLMUnavailable("no LLM backend is configured")


class HeuristicStubBackend:
    """Deterministic stand-in for a model (D-10), no network.

    For every mapped source that no longer appears in the sample, it proposes the closest field
    that appears and is not yet referenced (``difflib``, cutoff 0.6). It reads the request's
    structured fields only; it cannot follow instructions, which is exactly why the pipeline must
    not rely on the backend's good behaviour: the constraints do that.
    """

    name = "heuristic-stub"
    cutoff = 0.6

    def complete(self, system: str, user: str) -> str:
        request = json.loads(user)
        fields = [f for f in request["sample"]["fields"] if isinstance(f, str)]
        referenced = set(request["mapping"]["referenced"])
        free = [f for f in fields if f not in referenced]
        operations: list[dict[str, str]] = []
        for missing in request["drift"]["missing_sources"]:
            match = difflib.get_close_matches(missing["source"], free, n=1, cutoff=self.cutoff)
            if not match:
                continue
            free.remove(match[0])
            if missing["kind"] == "metric":
                operations.append(
                    {"op": "rename_source", "metric": missing["name"], "to": match[0]}
                )
            else:
                operations.append(
                    {"op": "rename_time_source", "field": missing["name"], "to": match[0]}
                )
        rationale = (
            "renamed each missing source to the closest unreferenced field in the sample"
            if operations
            else "no unreferenced field is close enough to a missing source"
        )
        return json.dumps({"operations": operations, "rationale": rationale})
