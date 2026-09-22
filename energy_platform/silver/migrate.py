"""Programmatic Alembic entry points; no ``alembic.ini`` and no shell (ADR-027 §3)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, urlsplit

import psycopg
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from psycopg import sql
from sqlalchemy import create_engine

MIGRATIONS = Path(__file__).parent / "migrations"
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def sqlalchemy_url(dsn: str, *, schema: str | None = None) -> str:
    """``postgresql://…`` (libpq form) → ``postgresql+psycopg://…`` for Alembic's engine;
    ``schema`` adds ``options=-c search_path=<schema>`` so the migrations (and Alembic's own
    version table) land in that schema."""
    scheme = urlsplit(dsn).scheme
    if scheme in {"postgresql", "postgres"}:
        url = "postgresql+psycopg:" + dsn[len(scheme) + 1 :]  # keep '///' for socket DSNs
    elif scheme == "postgresql+psycopg":
        url = dsn
    else:
        raise ValueError(f"not a PostgreSQL DSN: {dsn!r}")
    if schema is not None:
        options = quote(f"-c search_path={schema_name(schema)}", safe="")
        url += ("&" if "?" in url else "?") + f"options={options}"
    return url


def schema_name(name: str) -> str:
    """A schema name safe for ``search_path`` and ``sql.Identifier`` alike."""
    if not _SCHEMA_NAME.match(name):
        raise ValueError(f"{name!r} is not a plain lowercase schema name")
    return name


def _config(dsn: str, schema: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    # ConfigParser interpolation: a literal % (URL-encoded options) must be written as %%
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(dsn, schema=schema).replace("%", "%%"))
    return cfg


def upgrade(dsn: str, revision: str = "head", *, schema: str | None = None) -> None:
    command.upgrade(_config(dsn, schema), revision)


def downgrade(dsn: str, revision: str = "base", *, schema: str | None = None) -> None:
    command.downgrade(_config(dsn, schema), revision)


def create_schema(dsn: str, name: str) -> None:
    """``CREATE SCHEMA`` for a throwaway smoke schema (P5-D5); fails if it exists."""
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name(name))))


def drop_schema(dsn: str, name: str) -> None:
    """``DROP SCHEMA … CASCADE`` — only ever called on a schema this process created."""
    with psycopg.connect(dsn) as conn:
        conn.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name(name)))
        )


def current_revision(dsn: str, *, schema: str | None = None) -> str | None:
    engine = create_engine(sqlalchemy_url(dsn, schema=schema))
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
