import re
from pathlib import Path

from backend.app.db.migrations import (
    EXPECTED_P2_COLUMNS,
    EXPECTED_P2_TABLES,
    REQUIRED_P2_CONSTRAINTS,
    migration_statements,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "001_init.sql"


def test_initial_migration_has_exact_p2_tables_and_no_p3_or_destructive_sql() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    tables = set(
        re.findall(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.([a-z_]+)",
            sql,
            flags=re.IGNORECASE,
        )
    )

    assert tables == EXPECTED_P2_TABLES
    assert re.search(r"\b(VECTOR|DROP|TRUNCATE|DELETE)\b", sql, re.IGNORECASE) is None
    assert "CREATE VECTOR INDEX" not in sql.upper()


def test_migration_is_idempotent_and_split_into_single_schema_changes() -> None:
    statements = migration_statements(MIGRATION)

    assert len(statements) > len(EXPECTED_P2_TABLES)
    assert all(
        statement.upper().startswith(("CREATE TABLE IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS"))
        for statement in statements
    )


def test_migration_preserves_trace_and_checkpoint_order() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert sql.count("trace_order INT NOT NULL") == 3
    assert "UNIQUE (experiment_run_id, step_no)" in sql
    assert "ORDER BY" not in sql


def test_migration_defines_every_verified_column_and_constraint() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for table, columns in EXPECTED_P2_COLUMNS.items():
        match = re.search(
            rf"CREATE TABLE IF NOT EXISTS public\.{table} \((.*?)\n\);",
            sql,
            flags=re.DOTALL,
        )
        assert match is not None
        block = match.group(1)
        for column in columns:
            assert re.search(rf"^\s+{column}\s", block, flags=re.MULTILINE) is not None
    constraints = set(re.findall(r"CONSTRAINT\s+([a-z_]+)", sql))
    assert constraints >= REQUIRED_P2_CONSTRAINTS


def test_psycopg_is_the_only_runtime_database_dependency() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()

    assert '"psycopg[binary]>=3.2,<4"' in pyproject
    assert "sqlalchemy" not in pyproject
