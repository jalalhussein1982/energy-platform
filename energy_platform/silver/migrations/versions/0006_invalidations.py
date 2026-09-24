"""Durable invalidation decisions (ADR-038; review 2 DC-07).

``invalidations`` mirrors the Bronze ``invalidations/`` objects (``reconcile`` syncs them). The
current views drop every occurrence produced by an invalidated capture (for the invalidated
derivation, or all of them), so a version with no valid occurrence left disappears from the
current view without any row being deleted.

Revision ID: 0006_invalidations
Revises: 0005_occurrences
"""

from __future__ import annotations

from alembic import op

revision = "0006_invalidations"
down_revision = "0005_occurrences"
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE invalidations (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target_id      text         NOT NULL,
    capture_id     text         NOT NULL,
    derivation_id  char(16)     CHECK (derivation_id IS NULL OR derivation_id ~ '^[0-9a-f]{16}$'),
    reason         text         NOT NULL,
    recorded_by    text         NOT NULL,
    recorded_at    timestamptz  NOT NULL,
    UNIQUE NULLS NOT DISTINCT (target_id, capture_id, derivation_id)
);
CREATE INDEX invalidations_capture_idx ON invalidations (capture_id);
COMMENT ON TABLE invalidations IS
    'ADR-038: captures whose output is never current, replayed or restored; mirrored from Bronze';

DROP VIEW observations_current_by_transport;
DROP VIEW observations_current;

-- occurrences that survive: not produced by an invalidated capture (for this derivation)
CREATE VIEW observation_occurrences_valid AS
SELECT oc.observation_id, oc.run_attempt_id, oc.fetched_at, oc.source_published_at
FROM observation_occurrences oc
JOIN observations ob ON ob.id = oc.observation_id
JOIN run_attempts a ON a.id = oc.run_attempt_id
WHERE NOT EXISTS (
    SELECT 1 FROM invalidations i
    WHERE i.capture_id = a.capture_id
      AND (i.derivation_id IS NULL OR i.derivation_id = ob.derivation_id));

CREATE VIEW observations_current AS
SELECT DISTINCT ON (o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
                    o.source_version)
    o.*,
    CASE WHEN o.source_published_at IS NOT NULL THEN 'source_published_at'
         ELSE 'fetched_at' END AS ordering_basis
FROM observations o
JOIN derivations d ON d.derivation_id = o.derivation_id
JOIN (SELECT observation_id, max(COALESCE(source_published_at, fetched_at)) AS newest
      FROM observation_occurrences_valid GROUP BY observation_id) occ ON occ.observation_id = o.id
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
      FROM observation_occurrences_valid GROUP BY observation_id) occ ON occ.observation_id = o.id
ORDER BY o.dataset_id, o.dimensions, o.delivery_start_utc, o.resolution, o.metric,
         o.source_version, o.source_transport,
         occ.newest DESC,
         string_to_array(o.contract_version, '.')::int[] DESC,
         d.registered_at DESC,
         o.derivation_id DESC;
"""

# the 0005 views, verbatim
_DOWN = """
DROP VIEW observations_current_by_transport;
DROP VIEW observations_current;
DROP VIEW observation_occurrences_valid;
DROP TABLE invalidations;

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


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
