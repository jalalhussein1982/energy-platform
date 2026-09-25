"""Review 3 R5 and R6 on PostgreSQL: the reviewer reproduced both on the temporary server
(``codex-review/evidence/recovery-probes-postgres.json``); the fixed drill must pass there
too. Live is the ``postgres_store`` fixture's schema, scratch a throwaway schema on the same
server, dropped afterwards."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from energy_platform.bronze import Bronze, MemoryBlobStore, MemoryCaptureLog
from energy_platform.bronze.fixtures import load_fixture
from energy_platform.contracts.manifest import load_manifest
from energy_platform.parse import parser_ref
from energy_platform.runtime import capture, process, replay_range, restore_drill
from energy_platform.silver.migrate import create_schema, upgrade
from energy_platform.store import derivation_for
from energy_platform.store.postgres import PostgresStore
from tests.runtime.harness import SCHEDULED, T1, Clock, runtime

pytestmark = pytest.mark.db


@pytest.fixture
def scratch_store(migrated_dsn: str) -> Iterator[PostgresStore]:
    name = "review3_scratch"
    with psycopg.connect(migrated_dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))
    create_schema(migrated_dsn, name)
    upgrade(migrated_dsn, schema=name)
    store = PostgresStore(migrated_dsn, schema=name)
    try:
        yield store
    finally:
        store.close()
        with psycopg.connect(migrated_dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))


def test_review3_r5_shared_dataset_targets_pass_a_fresh_rebuild_on_postgres(
    postgres_store: PostgresStore, scratch_store: PostgresStore
) -> None:
    bronze = Bronze(MemoryBlobStore(), MemoryCaptureLog())
    manifests = []
    for target, fixture in (
        ("ote_imbalance_settlement", "ordinary_day"),
        ("ote_imbalance_settlement_monthly", "march_2026_month"),
    ):
        m = load_manifest(Path("targets") / target / "manifest.yaml")
        entry, payload = load_fixture(Path("targets") / target / "fixtures" / fixture)
        bronze.ingest(entry, payload)
        rt = runtime(
            m,
            store=postgres_store,
            bronze=bronze,
            clock=Clock(entry.fetched_at + timedelta(minutes=1)),
            payload=payload,
        )
        assert all(r.outcome in {"ok", "noop"} for r in process(rt))
        manifests.append(m)
    newest = max(e.fetched_at for m in manifests for e in bronze.log.list(m.target_id))
    clock = Clock(newest + timedelta(days=1))
    report = restore_drill(
        manifests, scratch=scratch_store, replica=bronze, live=postgres_store, clock=clock
    )
    assert report.ok, [t.message for t in report.targets]
    daily, monthly = report.targets
    assert daily.live is not None and daily.live.rows == 288 and daily.scratch == daily.live
    assert monthly.live is not None and monthly.live.rows == 8916
    assert monthly.scratch == monthly.live and monthly.message.startswith("identical")


def test_review3_r6_a_mapping_revision_is_history_on_postgres(
    postgres_store: PostgresStore, scratch_store: PostgresStore
) -> None:
    rt = runtime(T1, store=postgres_store)
    assert capture(rt, SCHEDULED).outcome == "ok"
    assert process(rt)[0].outcome == "ok"
    changed = T1.model_copy(
        update={
            "mapping": T1.mapping.model_copy(
                update={"ignore_fields": (*T1.mapping.ignore_fields, "DisplayNote")}
            )
        }
    )
    assert derivation_for(T1, parser_ref(T1)) != derivation_for(changed, parser_ref(changed))
    rt2 = runtime(changed, store=postgres_store, bronze=rt.bronze, clock=rt.clock)  # type: ignore[arg-type]
    rt.clock.advance(timedelta(seconds=1))  # type: ignore[attr-defined]
    replay_range(rt2, SCHEDULED, SCHEDULED + timedelta(minutes=1))
    process(rt2)
    assert len(postgres_store.all_rows(T1.contract.dataset_id)) == 384
    report = restore_drill(
        [changed], scratch=scratch_store, replica=rt.bronze, live=postgres_store, clock=rt.clock
    )
    t = report.targets[0]
    assert report.ok, t.message
    assert t.historical_versions == 192 and t.historical_derivations == 1
    assert t.missing_versions == 0 and t.diverging_versions == 0
