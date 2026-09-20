"""Store fixtures: the memory store always; Postgres when ``ENERGY_PLATFORM_TEST_DSN`` is set.

``make db-test`` starts an ephemeral server (``scripts/with_postgres.sh``) and runs the ``db``
marked tests; without the variable they are skipped, visibly. libpq opens its own sockets, so
the ADR-027 Python socket block does not interfere and no network is ever involved (Unix
socket, local server).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from energy_platform.silver.migrate import upgrade
from energy_platform.store import MemoryStore, Store
from energy_platform.store.postgres import PostgresStore

DSN = os.environ.get("ENERGY_PLATFORM_TEST_DSN")


@pytest.fixture(scope="session")
def migrated_dsn() -> str:
    if not DSN:
        pytest.skip("ENERGY_PLATFORM_TEST_DSN not set; run `make db-test`")
    upgrade(DSN)
    return DSN


@pytest.fixture
def postgres_store(migrated_dsn: str) -> Iterator[PostgresStore]:
    store = PostgresStore(migrated_dsn)
    store.truncate_all()
    try:
        yield store
    finally:
        store.close()


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
def store(request: pytest.FixtureRequest) -> Store:
    if request.param == "memory":
        return MemoryStore()
    postgres: PostgresStore = request.getfixturevalue("postgres_store")
    return postgres
