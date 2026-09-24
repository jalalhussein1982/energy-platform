"""ADR-016 §3: every migration has a downgrade; ``upgrade → downgrade base → upgrade`` is clean."""

from __future__ import annotations

import pytest

from energy_platform.silver.migrate import current_revision, downgrade, sqlalchemy_url, upgrade
from energy_platform.store.postgres import PostgresStore

pytestmark = pytest.mark.db

TABLES = (
    "derivations",
    "observation_occurrences",
    "observations",
    "quality_events",
    "run_attempts",
    "runs",
)


def test_sqlalchemy_url_maps_the_libpq_dsn() -> None:
    assert sqlalchemy_url("postgresql:///postgres?host=/tmp/x&user=postgres") == (
        "postgresql+psycopg:///postgres?host=/tmp/x&user=postgres"
    )
    assert sqlalchemy_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    with pytest.raises(ValueError, match="not a PostgreSQL DSN"):
        sqlalchemy_url("mysql://x")


def test_upgrade_downgrade_upgrade_round_trip(migrated_dsn: str) -> None:
    store = PostgresStore(migrated_dsn)
    try:
        assert current_revision(migrated_dsn) == "0005_occurrences"
        assert all(t in store.table_names() for t in TABLES)
        downgrade(migrated_dsn, "0001_ledger")
        assert current_revision(migrated_dsn) == "0001_ledger"
        assert "observations" not in store.table_names() and "runs" in store.table_names()
        downgrade(migrated_dsn, "base")
        assert current_revision(migrated_dsn) is None
        assert not any(t in store.table_names() for t in TABLES)
        upgrade(migrated_dsn)
        assert current_revision(migrated_dsn) == "0005_occurrences"
        assert all(t in store.table_names() for t in TABLES)
    finally:
        store.close()


def test_server_version_gate(migrated_dsn: str) -> None:
    store = PostgresStore(migrated_dsn)
    store.close()
