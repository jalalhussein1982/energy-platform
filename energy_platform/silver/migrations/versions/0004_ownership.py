"""Metric ownership in the current view (ADR-023 amendment 1; review 2 DC-03; 01 §3 rule 2).

``observations.owner_transport`` records, per row, which transport the registry names as the
system of record for the row's metric (NULL when none). ``observations_current`` ranks the
owner's rows first; ``observations_current_by_transport`` is the per-transport current view
(the reconciliation copy stays selectable). Existing rows are backfilled from the registry.

Revision ID: 0004_ownership
Revises: 0003_freshness
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from energy_platform.contracts.registry import DATASETS

revision = "0004_ownership"
down_revision = "0003_freshness"
branch_labels = None
depends_on = None

_ADD_COLUMN = """
ALTER TABLE observations ADD COLUMN owner_transport text
    CHECK (owner_transport IS NULL OR owner_transport IN ('soap', 'xlsx', 'html', 'rest'));
"""

# ADR-023 amendment 1: per observation identity the owning transport's row ranks first, then
# the ADR-023 §3 order (ordering basis, contract semver, derivation registration, derivation id).
_VIEWS_UP = """
DROP VIEW observations_current;
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

-- the per-transport current row: the reconciliation copy of an owned metric stays selectable
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

# the 0002 view, verbatim
_VIEWS_DOWN = """
DROP VIEW observations_current_by_transport;
DROP VIEW observations_current;
ALTER TABLE observations DROP COLUMN owner_transport;
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

_BACKFILL = text(
    "UPDATE observations SET owner_transport = :owner "
    "WHERE dataset_id = :dataset_id AND metric = :metric"
)


def upgrade() -> None:
    op.execute(_ADD_COLUMN)
    conn = op.get_bind()
    for contract in DATASETS.values():
        for spec in contract.metrics.values():
            if spec.owner_transport is None:
                continue
            conn.execute(
                _BACKFILL,
                {
                    "owner": spec.owner_transport,
                    "dataset_id": contract.dataset_id,
                    "metric": spec.name,
                },
            )
    op.execute(_VIEWS_UP)


def downgrade() -> None:
    op.execute(_VIEWS_DOWN)
