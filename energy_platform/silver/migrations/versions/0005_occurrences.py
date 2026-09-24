"""Observation occurrences (ADR-023 amendment 2; review 2 DC-04).

A Silver version row (observation identity + payload + derivation) is inserted once; every
capture that produces it again adds an **occurrence** (append-only). The current view orders a
version by its newest occurrence, so a provider's return to an earlier payload (A → B → A)
makes A current again, while replaying an older capture (its own ``fetched_at``) never outranks
a newer one. Existing rows get one occurrence each from their own capture.

Revision ID: 0005_occurrences
Revises: 0004_ownership
"""

from __future__ import annotations

from alembic import op

revision = "0005_occurrences"
down_revision = "0004_ownership"
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE observation_occurrences (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_id       bigint       NOT NULL REFERENCES observations (id),
    run_attempt_id       bigint       NOT NULL REFERENCES run_attempts (id),
    fetched_at           timestamptz  NOT NULL,
    source_published_at  timestamptz,
    UNIQUE (observation_id, fetched_at)
);
COMMENT ON TABLE observation_occurrences IS
    'ADR-023 amendment 2: every capture that produced a Silver version; ordering by the newest';

INSERT INTO observation_occurrences (observation_id, run_attempt_id, fetched_at,
                                     source_published_at)
SELECT id, run_attempt_id, fetched_at, source_published_at FROM observations;

DROP VIEW observations_current_by_transport;
DROP VIEW observations_current;

CREATE VIEW observations_current AS
SELECT DISTINCT ON (o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
                    o.source_version)
    o.*,
    CASE WHEN o.source_published_at IS NOT NULL THEN 'source_published_at'
         ELSE 'fetched_at' END AS ordering_basis
FROM observations o
JOIN derivations d ON d.derivation_id = o.derivation_id
JOIN (SELECT observation_id, max(COALESCE(source_published_at, fetched_at)) AS newest
      FROM observation_occurrences GROUP BY observation_id) occ ON occ.observation_id = o.id
ORDER BY o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
         o.source_version,
         CASE WHEN o.owner_transport IS NULL OR o.source_transport = o.owner_transport
              THEN 0 ELSE 1 END,
         occ.newest DESC,
         string_to_array(o.contract_version, '.')::int[] DESC,
         d.registered_at DESC,
         o.derivation_id DESC;

CREATE VIEW observations_current_by_transport AS
SELECT DISTINCT ON (o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
                    o.source_version, o.source_transport)
    o.*,
    CASE WHEN o.source_published_at IS NOT NULL THEN 'source_published_at'
         ELSE 'fetched_at' END AS ordering_basis
FROM observations o
JOIN derivations d ON d.derivation_id = o.derivation_id
JOIN (SELECT observation_id, max(COALESCE(source_published_at, fetched_at)) AS newest
      FROM observation_occurrences GROUP BY observation_id) occ ON occ.observation_id = o.id
ORDER BY o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
         o.source_version, o.source_transport,
         occ.newest DESC,
         string_to_array(o.contract_version, '.')::int[] DESC,
         d.registered_at DESC,
         o.derivation_id DESC;
"""

# the 0004 views, verbatim
_DOWN = """
DROP VIEW observations_current_by_transport;
DROP VIEW observations_current;
DROP TABLE observation_occurrences;

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
         CASE WHEN o.owner_transport IS NULL OR o.source_transport = o.owner_transport
              THEN 0 ELSE 1 END,
         COALESCE(o.source_published_at, o.fetched_at) DESC,
         string_to_array(o.contract_version, '.')::int[] DESC,
         d.registered_at DESC,
         o.derivation_id DESC;

CREATE VIEW observations_current_by_transport AS
SELECT DISTINCT ON (o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
                    o.source_version, o.source_transport)
    o.*,
    CASE WHEN o.source_published_at IS NOT NULL THEN 'source_published_at'
         ELSE 'fetched_at' END AS ordering_basis
FROM observations o
JOIN derivations d ON d.derivation_id = o.derivation_id
ORDER BY o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
         o.source_version, o.source_transport,
         COALESCE(o.source_published_at, o.fetched_at) DESC,
         string_to_array(o.contract_version, '.')::int[] DESC,
         d.registered_at DESC,
         o.derivation_id DESC;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
