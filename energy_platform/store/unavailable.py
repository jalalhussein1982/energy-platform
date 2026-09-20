"""A store that is never there: what ``capture`` runs against when no database is configured.

ADR-024 §1: the capture path needs no database. Every method raises ``StoreUnavailable``, so
the ledger acknowledgement is skipped with a warning and ``reconcile`` catches up later.
"""

from __future__ import annotations

from typing import Any, NoReturn

from energy_platform.store.protocol import StoreUnavailable


class UnavailableStore:
    """Implements the ``Store`` protocol by refusing every call."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)

        def refuse(*_args: Any, **_kwargs: Any) -> NoReturn:
            raise StoreUnavailable("no database configured (set ENERGY_PLATFORM_DSN or --dsn)")

        return refuse
