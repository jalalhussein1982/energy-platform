"""A read-only reader role for dashboards (ADR-039; Phase 11).

``energy_reader`` is a NOLOGIN group role with ``SELECT`` on every table and view of the
schema being migrated, and on every table created there later (default privileges). Login
roles (Grafana's ``grafana``) are created by ``energyctl migrate --reader-user`` with a password
from the environment, never here. A database user without ``CREATEROLE`` (cnpg / external
modes with a plain application user) gets a notice, not a failure: the dashboards then need an
operator-created role, which the runbook says.

Revision ID: 0007_reader_role
Revises: 0006_invalidations
"""

from __future__ import annotations

from alembic import op

revision = "0007_reader_role"
down_revision = "0006_invalidations"
branch_labels = None
depends_on = None

_UP = """
DO $$
DECLARE
    s text := current_schema();
BEGIN
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'energy_reader') THEN
            CREATE ROLE energy_reader NOLOGIN;
        END IF;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'energy_reader not created: no CREATEROLE (ADR-039: an operator creates it)';
        RETURN;
    END;
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO energy_reader', s);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO energy_reader', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
                   || 'GRANT SELECT ON TABLES TO energy_reader', s);
END $$;
"""

_DOWN = """
DO $$
DECLARE
    s text := current_schema();
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'energy_reader') THEN
        RETURN;
    END IF;
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
                   || 'REVOKE SELECT ON TABLES FROM energy_reader', s);
    EXECUTE format('REVOKE SELECT ON ALL TABLES IN SCHEMA %I FROM energy_reader', s);
    EXECUTE format('REVOKE USAGE ON SCHEMA %I FROM energy_reader', s);
END $$;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # the group role itself stays (other schemas may use it); its grants on this schema go
    op.execute(_DOWN)
