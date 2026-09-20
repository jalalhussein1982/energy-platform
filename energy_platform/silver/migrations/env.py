"""Alembic environment: online migrations over the URL the platform passes in."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url") or ""
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline (SQL script) mode is not used; run against a database")
run_migrations_online()
