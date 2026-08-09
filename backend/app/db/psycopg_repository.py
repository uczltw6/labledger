"""Psycopg 3 implementation of LabLedger structured memory."""

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.db.repository import (
    RepositoryConflictError,
    run_with_serialization_retry,
    validate_action_step_commit,
    validate_staged_action,
)
from backend.app.db.types import (
    ActionRecord,
    ActionStepCommit,
    AuditEventRecord,
    CalibrationRecord,
    CheckpointRecord,
    DeviceRecord,
    ExperimentRunRecord,
    HeroSeed,
    JSONObject,
    MemoryRecord,
    ObservationRecord,
    OutcomeRecord,
    RunRestore,
    StagedAction,
    TimelineRecord,
    TraceRows,
)

type DbConnection = psycopg.Connection[dict[str, Any]]


def _json_object(value: Any) -> JSONObject:
    if not isinstance(value, dict):
        raise TypeError("database JSON value must be an object")
    return cast(JSONObject, deepcopy(value))


class PsycopgStructuredMemoryRepository:
    """Parameterized SQL repository with bounded full-transaction retries."""

    def __init__(
        self,
        database_url: str,
        *,
        max_attempts: int = 3,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if not database_url:
            raise ValueError("database_url must not be empty")
        self._database_url = database_url
        self._max_attempts = max_attempts
        self._sleeper = sleeper

    def _transaction[T](self, operation: Callable[[DbConnection], T]) -> T:
        def attempt() -> T:
            with (
                psycopg.connect(
                    self._database_url,
                    autocommit=True,
                    row_factory=dict_row,
                ) as connection,
                connection.transaction(),
            ):
                return operation(connection)

        options: dict[str, Any] = {"max_attempts": self._max_attempts}
        if self._sleeper is not None:
            options["sleeper"] = self._sleeper
        return run_with_serialization_retry(attempt, **options)

    @staticmethod
    def _upsert_device(connection: DbConnection, record: DeviceRecord) -> None:
        connection.execute(
            """
            INSERT INTO public.devices (
                id, lab_id, name, device_type, vendor, model, resource_hint,
                connection_state, active_calibration_id, metadata, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                connection_state = excluded.connection_state,
                resource_hint = excluded.resource_hint,
                active_calibration_id = COALESCE(
                    excluded.active_calibration_id,
                    public.devices.active_calibration_id
                ),
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (
                record.id,
                record.lab_id,
                record.name,
                record.device_type,
                record.vendor,
                record.model,
                record.resource_hint,
                record.connection_state,
                record.active_calibration_id,
                Jsonb(record.metadata),
                record.created_at,
                record.updated_at,
            ),
        )

    @staticmethod
    def _insert_run(
        connection: DbConnection,
        record: ExperimentRunRecord,
        *,
        idempotent: bool,
    ) -> bool:
        suffix = " ON CONFLICT (id) DO NOTHING" if idempotent else ""
        inserted = connection.execute(
            """
            INSERT INTO public.experiment_runs (
                id, name, status, recipe_version, started_at, ended_at,
                current_step, context, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            + suffix
            + " RETURNING id",
            (
                record.id,
                record.name,
                record.status,
                record.recipe_version,
                record.started_at,
                record.ended_at,
                record.current_step,
                Jsonb(record.context),
                record.created_by,
            ),
        ).fetchone()
        if inserted is not None:
            return True
        existing = connection.execute(
            "SELECT context FROM public.experiment_runs WHERE id = %s",
            (record.id,),
        ).fetchone()
        if existing is None:
            raise RepositoryConflictError("run conflict could not be reloaded")
        existing_context = _json_object(existing["context"])
        identity_fields = ("persistence_fingerprint", "mapping_version")
        if all(
            existing_context.get(field) == record.context.get(field) for field in identity_fields
        ):
            return False
        raise RepositoryConflictError("run ID already contains different trace evidence")

    @staticmethod
    def _insert_observation(connection: DbConnection, record: ObservationRecord) -> None:
        connection.execute(
            """
            INSERT INTO public.observations (
                id, experiment_run_id, device_id, trace_order, observation_type,
                payload, summary, severity, observed_at, provenance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                record.id,
                record.experiment_run_id,
                record.device_id,
                record.trace_order,
                record.observation_type,
                Jsonb(record.payload),
                record.summary,
                record.severity,
                record.observed_at,
                Jsonb(record.provenance),
            ),
        )

    @staticmethod
    def _insert_action(
        connection: DbConnection,
        record: ActionRecord,
        *,
        idempotent: bool,
    ) -> None:
        suffix = " ON CONFLICT (id) DO NOTHING" if idempotent else ""
        connection.execute(
            """
            INSERT INTO public.actions (
                id, experiment_run_id, device_id, trace_order, action_type,
                parameters, risk_level, approval_state, selected_reason,
                memory_ids, status, created_at, executed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            + suffix,
            (
                record.id,
                record.experiment_run_id,
                record.device_id,
                record.trace_order,
                record.action_type,
                Jsonb(record.parameters),
                record.risk_level,
                record.approval_state,
                record.selected_reason,
                list(record.memory_ids),
                record.status,
                record.created_at,
                record.executed_at,
            ),
        )

    @staticmethod
    def _insert_outcome(
        connection: DbConnection,
        record: OutcomeRecord,
        *,
        idempotent: bool,
    ) -> None:
        suffix = " ON CONFLICT (id) DO NOTHING" if idempotent else ""
        connection.execute(
            """
            INSERT INTO public.outcomes (
                id, action_id, trace_order, success, result, quality_delta,
                error_code, summary, observed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            + suffix,
            (
                record.id,
                record.action_id,
                record.trace_order,
                record.success,
                Jsonb(record.result),
                record.quality_delta,
                record.error_code,
                record.summary,
                record.observed_at,
            ),
        )

    @staticmethod
    def _insert_checkpoint(
        connection: DbConnection,
        record: CheckpointRecord,
        *,
        idempotent: bool,
    ) -> None:
        suffix = " ON CONFLICT (id) DO NOTHING" if idempotent else ""
        connection.execute(
            """
            INSERT INTO public.agent_checkpoints (
                id, experiment_run_id, step_no, agent_state, last_action_id,
                pending_action_id, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            + suffix,
            (
                record.id,
                record.experiment_run_id,
                record.step_no,
                Jsonb(record.agent_state),
                record.last_action_id,
                record.pending_action_id,
                record.created_at,
            ),
        )

    @staticmethod
    def _insert_audit(
        connection: DbConnection,
        record: AuditEventRecord,
        *,
        idempotent: bool,
    ) -> None:
        suffix = " ON CONFLICT (id) DO NOTHING" if idempotent else ""
        connection.execute(
            """
            INSERT INTO public.audit_events (
                id, experiment_run_id, sequence_no, actor_type, actor_id,
                event_type, target_type, target_id, detail, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            + suffix,
            (
                record.id,
                record.experiment_run_id,
                record.sequence_no,
                record.actor_type,
                record.actor_id,
                record.event_type,
                record.target_type,
                record.target_id,
                Jsonb(record.detail),
                record.created_at,
            ),
        )

    def save_trace(self, rows: TraceRows) -> None:
        def operation(connection: DbConnection) -> None:
            inserted = self._insert_run(connection, rows.run, idempotent=True)
            if not inserted:
                return
            for device in rows.devices:
                self._upsert_device(connection, device)
            for observation in rows.observations:
                self._insert_observation(connection, observation)
            for action in rows.actions:
                self._insert_action(connection, action, idempotent=True)
            for outcome in rows.outcomes:
                self._insert_outcome(connection, outcome, idempotent=True)
            self._insert_checkpoint(connection, rows.checkpoint, idempotent=True)
            for audit in rows.audit_events:
                self._insert_audit(connection, audit, idempotent=True)

        self._transaction(operation)

    @staticmethod
    def _upsert_calibration(connection: DbConnection, record: CalibrationRecord) -> None:
        connection.execute(
            """
            INSERT INTO public.calibrations (
                id, device_id, version, parameters, status, valid_from,
                valid_until, superseded_by, confidence, provenance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                parameters = excluded.parameters,
                status = excluded.status,
                valid_from = excluded.valid_from,
                valid_until = excluded.valid_until,
                superseded_by = excluded.superseded_by,
                confidence = excluded.confidence,
                provenance = excluded.provenance
            """,
            (
                record.id,
                record.device_id,
                record.version,
                Jsonb(record.parameters),
                record.status,
                record.valid_from,
                record.valid_until,
                record.superseded_by,
                record.confidence,
                Jsonb(record.provenance),
            ),
        )

    @staticmethod
    def _upsert_memory(connection: DbConnection, record: MemoryRecord) -> None:
        connection.execute(
            """
            INSERT INTO public.memories (
                id, lab_id, experiment_run_id, device_id, memory_type, title,
                content, embedding_text, status, confidence, valid_from,
                valid_until, superseded_by, source_observation_id,
                source_action_id, source_outcome_id, provenance, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                embedding_text = excluded.embedding_text,
                status = excluded.status,
                confidence = excluded.confidence,
                valid_from = excluded.valid_from,
                valid_until = excluded.valid_until,
                superseded_by = excluded.superseded_by,
                provenance = excluded.provenance
            """,
            (
                record.id,
                record.lab_id,
                record.experiment_run_id,
                record.device_id,
                record.memory_type,
                record.title,
                record.content,
                record.embedding_text,
                record.status,
                record.confidence,
                record.valid_from,
                record.valid_until,
                record.superseded_by,
                record.source_observation_id,
                record.source_action_id,
                record.source_outcome_id,
                Jsonb(record.provenance),
                record.created_at,
            ),
        )

    def save_hero_seed(self, seed: HeroSeed) -> None:
        for trace in seed.traces:
            self.save_trace(trace)

        def operation(connection: DbConnection) -> None:
            for calibration in seed.calibrations:
                self._upsert_calibration(connection, calibration)
            for memory in sorted(seed.memories, key=lambda row: row.superseded_by is not None):
                self._upsert_memory(connection, memory)
            active_calibration_row = connection.execute(
                """
                SELECT id
                FROM public.calibrations
                WHERE id = %s AND device_id = %s AND status = 'active'
                """,
                (seed.active_calibration_id, seed.active_calibration_device_id),
            ).fetchone()
            if active_calibration_row is None:
                raise RepositoryConflictError(
                    "active calibration does not belong to the target device"
                )
            result = connection.execute(
                """
                UPDATE public.devices
                SET active_calibration_id = %s, updated_at = current_timestamp()
                WHERE id = %s
                """,
                (seed.active_calibration_id, seed.active_calibration_device_id),
            )
            if result.rowcount != 1:
                raise RepositoryConflictError("active-calibration device does not exist")

        self._transaction(operation)

    def stage_action(self, staged: StagedAction) -> None:
        validate_staged_action(staged)

        def operation(connection: DbConnection) -> None:
            for device in staged.devices:
                self._upsert_device(connection, device)
            self._insert_run(connection, staged.run, idempotent=False)
            self._insert_action(connection, staged.action, idempotent=False)
            self._insert_checkpoint(connection, staged.checkpoint, idempotent=False)
            self._insert_audit(connection, staged.audit_event, idempotent=False)

        self._transaction(operation)

    def commit_action_step(self, commit: ActionStepCommit) -> None:
        validate_action_step_commit(commit)

        def operation(connection: DbConnection) -> None:
            action_result = connection.execute(
                """
                UPDATE public.actions
                SET status = %s, executed_at = %s
                WHERE id = %s AND experiment_run_id = %s
                    AND status IN ('proposed', 'running')
                """,
                (commit.action_status, commit.executed_at, commit.action_id, commit.run_id),
            )
            if action_result.rowcount != 1:
                raise RepositoryConflictError(
                    "action is absent, terminal, or belongs to another run"
                )
            self._insert_outcome(connection, commit.outcome, idempotent=False)
            run_result = connection.execute(
                """
                UPDATE public.experiment_runs
                SET status = %s, current_step = %s, context = %s,
                    ended_at = CASE WHEN %s = 'completed' THEN %s ELSE ended_at END
                WHERE id = %s AND current_step = %s
                """,
                (
                    commit.run_status,
                    commit.next_step_no,
                    Jsonb(commit.run_context),
                    commit.run_status,
                    commit.executed_at,
                    commit.run_id,
                    commit.expected_step_no,
                ),
            )
            if run_result.rowcount != 1:
                raise RepositoryConflictError("run progress changed before commit")
            self._insert_checkpoint(connection, commit.checkpoint, idempotent=False)
            self._insert_audit(connection, commit.audit_event, idempotent=False)

        self._transaction(operation)

    @staticmethod
    def _load_run(connection: DbConnection, run_id: UUID) -> ExperimentRunRecord | None:
        row = connection.execute(
            """
            SELECT id, name, status, recipe_version, started_at, ended_at,
                   current_step, context, created_by
            FROM public.experiment_runs
            WHERE id = %s
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return ExperimentRunRecord(
            id=cast(UUID, row["id"]),
            name=str(row["name"]),
            status=str(row["status"]),
            recipe_version=str(row["recipe_version"]),
            started_at=cast(datetime | None, row["started_at"]),
            ended_at=cast(datetime | None, row["ended_at"]),
            current_step=int(row["current_step"]),
            context=_json_object(row["context"]),
            created_by=str(row["created_by"]),
        )

    @staticmethod
    def _load_checkpoint(connection: DbConnection, run_id: UUID) -> CheckpointRecord | None:
        row = connection.execute(
            """
            SELECT id, experiment_run_id, step_no, agent_state, last_action_id,
                   pending_action_id, created_at
            FROM public.agent_checkpoints
            WHERE experiment_run_id = %s
            ORDER BY step_no DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return CheckpointRecord(
            id=cast(UUID, row["id"]),
            experiment_run_id=cast(UUID, row["experiment_run_id"]),
            step_no=int(row["step_no"]),
            agent_state=_json_object(row["agent_state"]),
            last_action_id=cast(UUID | None, row["last_action_id"]),
            pending_action_id=cast(UUID | None, row["pending_action_id"]),
            created_at=cast(datetime, row["created_at"]),
        )

    @staticmethod
    def _load_timeline(connection: DbConnection, run_id: UUID) -> tuple[TimelineRecord, ...]:
        rows = connection.execute(
            """
            SELECT sequence_no, event_type, target_type, target_id, detail
            FROM public.audit_events
            WHERE experiment_run_id = %s AND sequence_no IS NOT NULL
            ORDER BY sequence_no ASC
            """,
            (run_id,),
        ).fetchall()
        return tuple(
            TimelineRecord(
                sequence_no=int(row["sequence_no"]),
                event_type=str(row["event_type"]),
                target_type=str(row["target_type"]),
                target_id=cast(UUID | None, row["target_id"]),
                detail=_json_object(row["detail"]),
            )
            for row in rows
        )

    def load_run(self, run_id: UUID) -> ExperimentRunRecord | None:
        return self._transaction(lambda connection: self._load_run(connection, run_id))

    def load_latest_checkpoint(self, run_id: UUID) -> CheckpointRecord | None:
        return self._transaction(lambda connection: self._load_checkpoint(connection, run_id))

    def load_timeline(self, run_id: UUID) -> tuple[TimelineRecord, ...]:
        return self._transaction(lambda connection: self._load_timeline(connection, run_id))

    def load_run_restore(self, run_id: UUID) -> RunRestore | None:
        def operation(connection: DbConnection) -> RunRestore | None:
            run = self._load_run(connection, run_id)
            checkpoint = self._load_checkpoint(connection, run_id)
            if run is None or checkpoint is None:
                return None
            counts = connection.execute(
                """
                SELECT
                    count(DISTINCT actions.id) AS action_count,
                    count(outcomes.id) AS outcome_count
                FROM public.actions
                LEFT JOIN public.outcomes ON outcomes.action_id = actions.id
                WHERE actions.experiment_run_id = %s
                """,
                (run_id,),
            ).fetchone()
            if counts is None:
                raise RuntimeError("count query returned no row")
            return RunRestore(
                run=run,
                checkpoint=checkpoint,
                timeline=self._load_timeline(connection, run_id),
                action_count=int(counts["action_count"]),
                outcome_count=int(counts["outcome_count"]),
            )

        return self._transaction(operation)
