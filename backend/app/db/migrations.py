"""Safe, non-destructive CockroachDB migration helpers."""

from pathlib import Path

import psycopg

EXPECTED_P2_TABLES = frozenset(
    {
        "actions",
        "agent_checkpoints",
        "artifacts",
        "audit_events",
        "calibrations",
        "device_sessions",
        "devices",
        "experiment_runs",
        "memories",
        "observations",
        "outcomes",
    }
)

EXPECTED_P2_COLUMNS: dict[str, frozenset[str]] = {
    "devices": frozenset(
        {
            "id",
            "lab_id",
            "name",
            "device_type",
            "vendor",
            "model",
            "resource_hint",
            "connection_state",
            "firmware_version",
            "active_calibration_id",
            "metadata",
            "created_at",
            "updated_at",
        }
    ),
    "experiment_runs": frozenset(
        {
            "id",
            "name",
            "status",
            "recipe_version",
            "started_at",
            "ended_at",
            "current_step",
            "context",
            "created_by",
        }
    ),
    "artifacts": frozenset(
        {
            "id",
            "experiment_run_id",
            "artifact_type",
            "s3_uri",
            "sha256",
            "metadata",
            "created_at",
        }
    ),
    "observations": frozenset(
        {
            "id",
            "experiment_run_id",
            "device_id",
            "trace_order",
            "observation_type",
            "payload",
            "summary",
            "severity",
            "observed_at",
            "artifact_id",
            "provenance",
        }
    ),
    "actions": frozenset(
        {
            "id",
            "experiment_run_id",
            "device_id",
            "trace_order",
            "action_type",
            "parameters",
            "risk_level",
            "approval_state",
            "selected_reason",
            "memory_ids",
            "status",
            "created_at",
            "executed_at",
        }
    ),
    "outcomes": frozenset(
        {
            "id",
            "action_id",
            "trace_order",
            "success",
            "result",
            "quality_delta",
            "error_code",
            "summary",
            "observed_at",
        }
    ),
    "calibrations": frozenset(
        {
            "id",
            "device_id",
            "version",
            "parameters",
            "status",
            "valid_from",
            "valid_until",
            "superseded_by",
            "confidence",
            "provenance",
        }
    ),
    "device_sessions": frozenset(
        {
            "id",
            "device_id",
            "experiment_run_id",
            "started_at",
            "ended_at",
            "connection_result",
            "identity_response",
            "error_code",
            "error_detail",
            "recovery_action_id",
        }
    ),
    "memories": frozenset(
        {
            "id",
            "lab_id",
            "experiment_run_id",
            "device_id",
            "memory_type",
            "title",
            "content",
            "embedding_text",
            "status",
            "confidence",
            "valid_from",
            "valid_until",
            "superseded_by",
            "source_observation_id",
            "source_action_id",
            "source_outcome_id",
            "provenance",
            "created_at",
        }
    ),
    "agent_checkpoints": frozenset(
        {
            "id",
            "experiment_run_id",
            "step_no",
            "agent_state",
            "last_action_id",
            "pending_action_id",
            "created_at",
        }
    ),
    "audit_events": frozenset(
        {
            "id",
            "experiment_run_id",
            "sequence_no",
            "actor_type",
            "actor_id",
            "event_type",
            "target_type",
            "target_id",
            "detail",
            "created_at",
        }
    ),
}

REQUIRED_P2_CONSTRAINTS = frozenset(
    {
        "uq_devices_lab_name",
        "ck_devices_connection_state",
        "ck_experiment_runs_status",
        "uq_observations_run_order",
        "uq_actions_run_order",
        "uq_outcomes_action",
        "uq_calibrations_device_version",
        "ck_calibrations_status",
        "ck_calibrations_confidence",
        "ck_memories_type",
        "ck_memories_status",
        "ck_memories_confidence",
        "uq_agent_checkpoints_run_step",
        "fk_agent_checkpoints_last_action",
        "fk_agent_checkpoints_pending_action",
        "uq_audit_events_run_sequence",
    }
)


def migration_statements(path: Path) -> tuple[str, ...]:
    """Split the repository-owned migration into individual schema changes."""

    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    ]
    return tuple(
        statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()
    )


def apply_migration(database_url: str, path: Path) -> None:
    """Apply each idempotent schema change in its own implicit transaction."""

    with psycopg.connect(database_url, autocommit=True) as connection:
        for statement in migration_statements(path):
            connection.execute(statement)


def verify_p2_schema(database_url: str) -> tuple[str, ...]:
    """Return human-safe schema errors without exposing connection details."""

    errors: list[str] = []
    with psycopg.connect(database_url) as connection:
        table_rows = connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = ANY(%s)
            """,
            ("public", list(EXPECTED_P2_TABLES)),
        ).fetchall()
        present = {str(row[0]) for row in table_rows}
        missing = sorted(EXPECTED_P2_TABLES - present)
        if missing:
            errors.append(f"missing P2 tables: {', '.join(missing)}")
        column_rows = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = ANY(%s)
            """,
            ("public", list(EXPECTED_P2_TABLES)),
        ).fetchall()
        actual_columns: dict[str, set[str]] = {table: set() for table in EXPECTED_P2_TABLES}
        id_types: dict[str, str] = {}
        for table_name, column_name, data_type in column_rows:
            table = str(table_name)
            column = str(column_name)
            actual_columns[table].add(column)
            if column == "id":
                id_types[table] = str(data_type).lower()
        for table, expected in EXPECTED_P2_COLUMNS.items():
            missing_columns = sorted(expected - actual_columns[table])
            if missing_columns:
                errors.append(f"{table} missing columns: {', '.join(missing_columns)}")
            if id_types.get(table) != "uuid":
                errors.append(f"{table}.id is not UUID")
        forbidden = [
            str(column_name)
            for table_name, column_name, data_type in column_rows
            if str(table_name) == "memories"
            and (str(column_name) == "embedding" or "vector" in str(data_type).lower())
        ]
        if forbidden:
            errors.append("P3 vector columns appeared in the P2 schema")
        constraint_rows = connection.execute(
            """
            SELECT table_name, constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_schema = %s AND table_name = ANY(%s)
            """,
            ("public", list(EXPECTED_P2_TABLES)),
        ).fetchall()
        constraints = {str(row[1]) for row in constraint_rows}
        missing_constraints = sorted(REQUIRED_P2_CONSTRAINTS - constraints)
        if missing_constraints:
            errors.append(f"missing constraints: {', '.join(missing_constraints)}")
        primary_key_tables = {
            str(table_name)
            for table_name, _constraint_name, constraint_type in constraint_rows
            if str(constraint_type).upper() == "PRIMARY KEY"
        }
        missing_primary_keys = sorted(EXPECTED_P2_TABLES - primary_key_tables)
        if missing_primary_keys:
            errors.append(f"missing primary keys: {', '.join(missing_primary_keys)}")
    return tuple(errors)
