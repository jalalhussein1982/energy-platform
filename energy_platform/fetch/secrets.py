"""``secretRef`` resolution (ADR-017 §secrets, 04 §3.4).

The manifest carries a reference; the platform resolves it at fetch time. In this phase the only
backend is the process environment (the ``local`` profile), keyed ``<NAME>_<KEY>`` upper-cased
with ``-`` and ``.`` mapped to ``_``. The value never appears in a URL that is logged or stored
(:func:`redact_query`).
"""

from __future__ import annotations

import os
import re
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from energy_platform.contracts.manifest import SecretRef, target_secret_name

REDACTED = "<redacted>"


class SecretMissing(LookupError):
    """The reference does not resolve; the request is not sent."""


class SecretResolver(Protocol):
    def resolve(self, ref: SecretRef) -> str: ...


def env_name(ref: SecretRef) -> str:
    return re.sub(r"[^A-Z0-9]", "_", f"{ref.name}_{ref.key}".upper())


class EnvSecretResolver:
    """``local`` profile backend: the value lives in the environment (never in the repository)."""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._env = os.environ if environ is None else environ

    def resolve(self, ref: SecretRef) -> str:
        name = env_name(ref)
        value = self._env.get(name)
        if not value:
            raise SecretMissing(
                f"secretRef {ref.name}/{ref.key}: environment variable {name} unset"
            )
        return value


class SecretOutOfScope(LookupError):
    """A target asked for a secret that is not its own (05 C-63); the request is not sent."""


class ScopedSecretResolver:
    """A target's view of the secrets: only ``target-<id>`` resolves, whatever the manifest says.

    Manifest validation refuses another name already; this holds for a manifest that never went
    through validation (``model_construct``) and for every caller of ``fetch_for_manifest``.
    """

    def __init__(self, target_id: str, inner: SecretResolver) -> None:
        self._name = target_secret_name(target_id)
        self._inner = inner

    def resolve(self, ref: SecretRef) -> str:
        if ref.name != self._name:
            raise SecretOutOfScope(
                f"secretRef {ref.name}/{ref.key}: a target may resolve only {self._name}/<key>"
            )
        return self._inner.resolve(ref)


def redact_query(url: str, params: tuple[str, ...]) -> str:
    """Replace the value of each named query parameter so the URL can be logged and stored."""
    if not params:
        return url
    parts = urlsplit(url)
    pairs = [(k, REDACTED if k in params else v) for k, v in parse_qsl(parts.query, True)]
    return urlunsplit(parts._replace(query=urlencode(pairs)))
