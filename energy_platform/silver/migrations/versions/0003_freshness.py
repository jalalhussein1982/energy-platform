"""Freshness SLI rows (ADR-037 / ADR-012; 01 §5): one row per target, upserted by ``freshness``.

Revision ID: 0003_freshness
Revises: 0002_silver
"""

from __future__ import annotations

from alembic import op

revision = "0003_freshness"
down_revision = "0002_silver"
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE target_freshness (
    target_id             text        PRIMARY KEY,
    computed_at           timestamptz NOT NULL,
    partition_start       timestamptz NOT NULL,
    partition_end         timestamptz NOT NULL CHECK (partition_end > partition_start),
    expected_by           timestamptz NOT NULL,
    status                text        NOT NULL CHECK (status IN ('pending', 'partial',
                                                                'late', 'complete')),
    observed_periods      integer     NOT NULL CHECK (observed_periods >= 0),
    expected_periods      integer     NOT NULL CHECK (expected_periods >= 1),
    newest_delivery_start timestamptz,
    last_capture_at       timestamptz,
    last_capture_outcome  text,
    stale_fetch_streak    integer     NOT NULL DEFAULT 0 CHECK (stale_fetch_streak >= 0),
    source_unavailable    boolean     NOT NULL DEFAULT false,
    pipeline_failed       boolean     NOT NULL DEFAULT false
);
COMMENT ON TABLE target_freshness IS
    'ADR-037: freshness SLI per target, read by the metrics exporter; rewritten every gap run';
"""

_DOWN = """
DROP TABLE target_freshness;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
