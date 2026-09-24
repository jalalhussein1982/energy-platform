"""ADR-016 §3: every migration has a downgrade; ``upgrade → downgrade base → upgrade`` is clean."""

from __future__ import annotations

import psycopg
import pytest

from energy_platform.silver.migrate import current_revision, downgrade, sqlalchemy_url, upgrade
from energy_platform.store.postgres import PostgresStore

pytestmark = pytest.mark.db

TABLES = (
    "derivations",
    "invalidations",
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
        assert current_revision(migrated_dsn) == "0007_reader_role"
        assert all(t in store.table_names() for t in TABLES)
        downgrade(migrated_dsn, "0001_ledger")
        assert current_revision(migrated_dsn) == "0001_ledger"
        assert "observations" not in store.table_names() and "runs" in store.table_names()
        downgrade(migrated_dsn, "base")
        assert current_revision(migrated_dsn) is None
        assert not any(t in store.table_names() for t in TABLES)
        upgrade(migrated_dsn)
        assert current_revision(migrated_dsn) == "0007_reader_role"
        assert all(t in store.table_names() for t in TABLES)
    finally:
        store.close()


def test_server_version_gate(migrated_dsn: str) -> None:
    store = PostgresStore(migrated_dsn)
    store.close()


def test_reader_role_can_select_and_cannot_write(migrated_dsn: str) -> None:
    """ADR-039 / migration 0007: the group role has SELECT on the schema; the login role the
    hook creates inherits it and nothing more. The ephemeral server has no TCP listener, so the
    reader connects over the same socket as the test user."""
    from urllib.parse import parse_qs, urlsplit

    from energy_platform.silver.migrate import grant_reader

    grant_reader(migrated_dsn, "grafana_test", "s3cret-reader")
    parts = urlsplit(migrated_dsn)
    host = parse_qs(parts.query).get("host", [None])[0]
    reader_dsn = f"postgresql://grafana_test:s3cret-reader@/{parts.path.lstrip('/')}" + (
        f"?host={host}" if host else ""
    )
    with psycopg.connect(reader_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM observations_current").fetchone() is not None
        assert conn.execute("SELECT count(*) FROM target_freshness").fetchone() is not None
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO derivations VALUES "
                "('0000000000000000', 'x', '1.0.0', '{}', 'p', now())"
            )
        conn.rollback()
    grant_reader(migrated_dsn, "grafana_test", "rotated")  # idempotent: rotates the password
    # (the ephemeral server trusts its Unix socket, so a wrong password cannot be proved here)
    with psycopg.connect(migrated_dsn) as conn:
        member = conn.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
            "JOIN pg_roles u ON u.oid = m.member WHERE g.rolname = 'energy_reader' "
            "AND u.rolname = 'grafana_test'"
        ).fetchone()
        assert member is not None
