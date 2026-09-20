"""Programmatic Alembic entry points; no ``alembic.ini`` and no shell (ADR-027 §3)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

MIGRATIONS = Path(__file__).parent / "migrations"


def sqlalchemy_url(dsn: str) -> str:
    """``postgresql://…`` (libpq form) → ``postgresql+psycopg://…`` for Alembic's engine."""
    scheme = urlsplit(dsn).scheme
    if scheme in {"postgresql", "postgres"}:
        return "postgresql+psycopg:" + dsn[len(scheme) + 1 :]  # keep '///' for socket DSNs
    if scheme == "postgresql+psycopg":
        return dsn
    raise ValueError(f"not a PostgreSQL DSN: {dsn!r}")


def _config(dsn: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(dsn))
    return cfg


def upgrade(dsn: str, revision: str = "head") -> None:
    command.upgrade(_config(dsn), revision)


def downgrade(dsn: str, revision: str = "base") -> None:
    command.downgrade(_config(dsn), revision)


def current_revision(dsn: str) -> str | None:
    engine = create_engine(sqlalchemy_url(dsn))
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
