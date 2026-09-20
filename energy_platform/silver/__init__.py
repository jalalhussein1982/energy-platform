"""Silver: the PostgreSQL schema and its migrations (ADR-018, ADR-023, ADR-024, ADR-030).

Every migration is explicit DDL with a downgrade (ADR-016 §3); ``make db-test`` exercises
``upgrade → downgrade base → upgrade`` on an ephemeral server. The store implementation lives
in ``energy_platform.store``.
"""

from energy_platform.silver.migrate import current_revision, downgrade, sqlalchemy_url, upgrade

__all__ = ["current_revision", "downgrade", "sqlalchemy_url", "upgrade"]
