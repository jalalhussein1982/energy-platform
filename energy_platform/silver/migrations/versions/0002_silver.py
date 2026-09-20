"""Silver observations, quality events and the current view (ADR-018, ADR-023 §2-§3, 01 §6).

Revision ID: 0002_silver
Revises: 0001_ledger
"""

from __future__ import annotations

from alembic import op

revision = "0002_silver"
down_revision = "0001_ledger"
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE observations (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- envelope (01 §6.1, ADR-023)
    source_id            text         NOT NULL,
    dataset_id           text         NOT NULL,
    source_transport     text         NOT NULL CHECK (source_transport IN ('soap', 'xlsx',
                                                                            'html', 'rest')),
    contract_version     text         NOT NULL
                                      CHECK (contract_version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'),
    derivation_id        char(16)     NOT NULL REFERENCES derivations (derivation_id),
    raw_ref              text         NOT NULL,
    payload_sha256       char(64)     NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    fetched_at           timestamptz  NOT NULL,
    source_published_at  timestamptz,
    source_version       text,
    processed_at         timestamptz  NOT NULL,
    -- time (01 §6.2, ADR-018)
    delivery_interval    tstzrange    NOT NULL CHECK (lower_inc(delivery_interval)
                                                     AND NOT upper_inc(delivery_interval)
                                                     AND NOT lower_inf(delivery_interval)
                                                     AND NOT upper_inf(delivery_interval)),
    delivery_start_utc   timestamptz  GENERATED ALWAYS AS (lower(delivery_interval)) STORED,
    resolution           text         NOT NULL,
    local_date           date         NOT NULL,
    period_index         integer      CHECK (period_index IS NULL OR period_index >= 1),
    kind                 text         NOT NULL CHECK (kind IN ('interval', 'point')),
    -- identity and value (01 §6.3, §9; metric-long, P1-D1)
    dimensions           jsonb        NOT NULL,
    metric               text         NOT NULL,
    value                numeric,
    unit                 text         NOT NULL,
    sign_convention      text         NOT NULL CHECK (sign_convention IN ('as_published',
                                                                          'inverted')),
    -- lineage (ADR-024 §3)
    run_attempt_id       bigint       NOT NULL REFERENCES run_attempts (id)
);

-- ADR-023 §2 version identity = observation identity + payload + derivation;
-- ADR-023 §5 NULL source_version is a value (NULLS NOT DISTINCT, PostgreSQL >= 15, ADR-030).
CREATE UNIQUE INDEX observations_version_identity
    ON observations (dataset_id, dimensions, delivery_start_utc, resolution, metric,
                     source_version, payload_sha256, derivation_id)
    NULLS NOT DISTINCT;
CREATE INDEX observations_dataset_time_idx ON observations (dataset_id, delivery_start_utc);
CREATE INDEX observations_derivation_idx ON observations (derivation_id);
CREATE INDEX observations_attempt_idx ON observations (run_attempt_id);

CREATE TABLE quality_events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target_id       text         NOT NULL,
    run_attempt_id  bigint       REFERENCES run_attempts (id),
    kind            text         NOT NULL,
    severity        text         NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
    message         text         NOT NULL,
    locator         text         NOT NULL DEFAULT '',
    metric          text,
    created_at      timestamptz  NOT NULL
);
CREATE INDEX quality_events_target_idx ON quality_events (target_id, kind);

-- ADR-023 §3: current row per observation identity by ordering basis, then contract semver,
-- then derivation registration, then derivation id. Nothing is updated in place.
CREATE VIEW observations_current AS
SELECT DISTINCT ON (o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
                    o.source_version)
    o.*,
    CASE WHEN o.source_published_at IS NOT NULL THEN 'source_published_at'
         ELSE 'fetched_at' END AS ordering_basis
FROM observations o
JOIN derivations d ON d.derivation_id = o.derivation_id
ORDER BY o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
         o.source_version,
         COALESCE(o.source_published_at, o.fetched_at) DESC,
         string_to_array(o.contract_version, '.')::int[] DESC,
         d.registered_at DESC,
         o.derivation_id DESC;
"""

_DOWN = """
DROP VIEW observations_current;
DROP TABLE quality_events;
DROP TABLE observations;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
