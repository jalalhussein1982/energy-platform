"""Run ledger and derivations (ADR-003 rev., ADR-023 §1, ADR-024 §3).

Revision ID: 0001_ledger
Revises: None
"""

from __future__ import annotations

from alembic import op

revision = "0001_ledger"
down_revision = None
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE derivations (
    derivation_id     char(16)     PRIMARY KEY CHECK (derivation_id ~ '^[0-9a-f]{16}$'),
    platform_version  text         NOT NULL,
    contract_version  text         NOT NULL,
    mapping_block     jsonb        NOT NULL,
    parser_ref        text         NOT NULL,
    registered_at     timestamptz  NOT NULL
);

CREATE TABLE runs (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target_id      text         NOT NULL,
    scheduled_for  timestamptz  NOT NULL,
    state          text         NOT NULL CHECK (state IN ('scheduled', 'captured', 'processed',
                                                          'failed', 'missing_capture',
                                                          'unrecoverable')),
    fence          bigint       NOT NULL DEFAULT 0,
    origin         text         NOT NULL CHECK (origin IN ('scheduled', 'reconciled', 'backfill',
                                                           'replay', 'manual')),
    lease_owner    text,
    lease_until    timestamptz,
    capture_id     text,
    created_at     timestamptz  NOT NULL,
    updated_at     timestamptz  NOT NULL,
    UNIQUE (target_id, scheduled_for)
);
CREATE INDEX runs_state_idx ON runs (target_id, state);

CREATE TABLE run_attempts (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id         bigint       NOT NULL REFERENCES runs (id),
    kind           text         NOT NULL CHECK (kind IN ('capture', 'process', 'backfill',
                                                         'replay')),
    lease_owner    text,
    lease_until    timestamptz,
    fence          bigint,
    capture_id     text,
    derivation_id  char(16)     REFERENCES derivations (derivation_id),
    outcome        text         CHECK (outcome IN ('ok', 'failed', 'lost_lease', 'quarantined',
                                                   'noop', 'source_unavailable')),
    error          text,
    started_at     timestamptz  NOT NULL,
    finished_at    timestamptz
);
CREATE INDEX run_attempts_run_idx ON run_attempts (run_id);
CREATE INDEX run_attempts_pending_replay_idx
    ON run_attempts (run_id) WHERE kind = 'replay' AND outcome IS NULL AND lease_owner IS NULL;
"""

_DOWN = """
DROP TABLE run_attempts;
DROP TABLE runs;
DROP TABLE derivations;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
