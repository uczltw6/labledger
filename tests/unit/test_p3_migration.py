from pathlib import Path

from backend.app.db.migrations import migration_statements
from backend.app.memory.schema import P3_VECTOR_INDEX, migration_dimension

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "002_vector_memory.sql"


def _normalized_sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_p3_migration_locks_vector_dimension_to_production_setting() -> None:
    assert migration_dimension(MIGRATION) == 512


def test_p3_migration_is_additive_repeatable_and_session_scoped() -> None:
    sql = _normalized_sql()
    assert "set sql_safe_updates = false" in sql
    assert "cluster setting" not in sql.replace("cluster-wide setting", "")
    assert sql.count("add column if not exists") == 4
    assert "create vector index if not exists" in sql
    assert P3_VECTOR_INDEX in sql
    assert "embedding vector_cosine_ops" in sql
    assert "drop " not in sql
    assert "truncate " not in sql
    assert "delete " not in sql


def test_p3_migration_splits_into_expected_executable_statements() -> None:
    statements = migration_statements(MIGRATION)
    assert len(statements) == 6
    assert statements[0].lower() == "set sql_safe_updates = false"
    assert statements[-1].lower().startswith("create vector index if not exists")
