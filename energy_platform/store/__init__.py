"""Persistence: the run ledger, derivations, Silver rows and quality events (plan P2-D3).

One ``Store`` protocol because fencing couples them: every Silver write and every state
transition for a run happens in one transaction predicated on ``runs.fence`` (ADR-024 §4).
``MemoryStore`` carries the unit tests and the ADR-023/ADR-024 proofs; ``PostgresStore`` is the
real thing (plain PostgreSQL >= 16, ADR-030) behind the Alembic migrations in
``energy_platform.silver.migrations``.
"""

from energy_platform.store.memory import MemoryStore
from energy_platform.store.protocol import (
    AttemptKind,
    AttemptOutcome,
    Claim,
    CommitResult,
    CurrentRow,
    Derivation,
    Run,
    RunAttempt,
    RunOrigin,
    RunState,
    Store,
    StoredEvent,
    StoredObservation,
    StoreUnavailable,
    derivation_for,
)

__all__ = [
    "AttemptKind",
    "AttemptOutcome",
    "Claim",
    "CommitResult",
    "CurrentRow",
    "Derivation",
    "MemoryStore",
    "Run",
    "RunAttempt",
    "RunOrigin",
    "RunState",
    "Store",
    "StoreUnavailable",
    "StoredEvent",
    "StoredObservation",
    "derivation_for",
]
