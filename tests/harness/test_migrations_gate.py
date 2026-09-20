"""05 C-45: a migration without a real downgrade fails statically (ADR-016 §3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_migrations import DEFAULT_DIR, check_directory, check_migration_text

GOOD = '''"""x"""
from alembic import op

revision = "0002_x"
down_revision = "0001_y"


def upgrade() -> None:
    op.execute("CREATE TABLE t (id int)")


def downgrade() -> None:
    op.execute("DROP TABLE t")
'''


def test_committed_migrations_pass() -> None:
    assert check_directory(DEFAULT_DIR) == []


def test_control_passes() -> None:
    problems, rev, down = check_migration_text(GOOD)
    assert problems == [] and rev == "0002_x" and down == "0001_y"


@pytest.mark.parametrize(
    "body",
    [
        "    pass\n",
        "    ...\n",
        '    """later"""\n',
        "    raise NotImplementedError\n",
        "    raise NotImplementedError('no')\n",
        '    """doc"""\n    pass\n',
    ],
)
def test_migration_without_downgrade_rejected(body: str) -> None:
    text = GOOD.replace('    op.execute("DROP TABLE t")\n', body)
    problems, _, _ = check_migration_text(text)
    assert any("placeholder" in p for p in problems), problems


def test_missing_downgrade_function_rejected() -> None:
    text = GOOD[: GOOD.index("def downgrade")]
    problems, _, _ = check_migration_text(text)
    assert any("no downgrade()" in p for p in problems)


def test_missing_revision_metadata_rejected() -> None:
    problems, _, _ = check_migration_text(GOOD.replace('revision = "0002_x"\n', ""))
    assert any("no `revision`" in p for p in problems)


def test_chain_must_be_linear(tmp_path: Path) -> None:
    (tmp_path / "0001_a.py").write_text(
        GOOD.replace('"0002_x"', '"0001_a"').replace('"0001_y"', "None")
    )
    (tmp_path / "0002_b.py").write_text(
        GOOD.replace('"0002_x"', '"0002_b"').replace('"0001_y"', '"0001_a"')
    )
    assert check_directory(tmp_path) == []
    (tmp_path / "0002_c.py").write_text(
        GOOD.replace('"0002_x"', '"0002_c"').replace('"0001_y"', '"0001_a"')
    )
    problems = check_directory(tmp_path)
    assert any("one head" in p for p in problems), problems
    (tmp_path / "0003_d.py").write_text(
        GOOD.replace('"0002_x"', '"0003_d"').replace('"0001_y"', '"nope"')
    )
    assert any("does not exist" in p for p in check_directory(tmp_path))


def test_empty_directory_is_a_failure(tmp_path: Path) -> None:
    assert check_directory(tmp_path) == [f"{tmp_path}: no migrations found"]
