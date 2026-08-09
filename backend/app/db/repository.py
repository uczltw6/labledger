"""Explicit repository interface and shared transaction retry behavior."""

from collections.abc import Callable
from time import sleep
from typing import Protocol
from uuid import UUID

from backend.app.db.types import (
    ActionStepCommit,
    CheckpointRecord,
    ExperimentRunRecord,
    HeroSeed,
    RunRestore,
    StagedAction,
    TimelineRecord,
    TraceRows,
)


class RepositoryConflictError(RuntimeError):
    """Raised when persisted progress does not match the caller's expectation."""


class TraceValidationError(ValueError):
    """Raised before SQL when a simulator trace is structurally inconsistent."""


class StructuredMemoryRepository(Protocol):
    """Storage contract implemented by CockroachDB and the local fake."""

    def save_trace(self, rows: TraceRows) -> None: ...

    def save_hero_seed(self, seed: HeroSeed) -> None: ...

    def stage_action(self, staged: StagedAction) -> None: ...

    def commit_action_step(self, commit: ActionStepCommit) -> None: ...

    def load_run(self, run_id: UUID) -> ExperimentRunRecord | None: ...

    def load_latest_checkpoint(self, run_id: UUID) -> CheckpointRecord | None: ...

    def load_timeline(self, run_id: UUID) -> tuple[TimelineRecord, ...]: ...

    def load_run_restore(self, run_id: UUID) -> RunRestore | None: ...


def validate_staged_action(staged: StagedAction) -> None:
    """Reject cross-run or incomplete pending-action state before persistence."""

    if staged.run.current_step != staged.checkpoint.step_no:
        raise RepositoryConflictError("initial checkpoint must match the run step")
    if staged.action.experiment_run_id != staged.run.id:
        raise RepositoryConflictError("staged action belongs to a different run")
    if staged.checkpoint.experiment_run_id != staged.run.id:
        raise RepositoryConflictError("staged checkpoint belongs to a different run")
    if staged.checkpoint.pending_action_id != staged.action.id:
        raise RepositoryConflictError("staged checkpoint must reference the pending action")
    if staged.audit_event.experiment_run_id != staged.run.id:
        raise RepositoryConflictError("staged audit belongs to a different run")
    if staged.audit_event.target_id != staged.action.id:
        raise RepositoryConflictError("staged audit must target the pending action")
    if staged.audit_event.sequence_no != staged.action.trace_order:
        raise RepositoryConflictError("staged audit order must match the pending action")
    if staged.action.device_id not in {device.id for device in staged.devices}:
        raise RepositoryConflictError("staged action device is missing from the device snapshot")
    state = staged.checkpoint.agent_state
    if state.get("current_step") != staged.run.current_step:
        raise RepositoryConflictError("staged checkpoint state has the wrong current step")
    if state.get("pending_action_id") != str(staged.action.id):
        raise RepositoryConflictError("staged checkpoint state lacks the pending action")


def validate_action_step_commit(commit: ActionStepCommit) -> None:
    """Validate every cross-record identity in the atomic terminal step."""

    if commit.next_step_no <= commit.expected_step_no:
        raise RepositoryConflictError("next step must advance run progress")
    if commit.outcome.action_id != commit.action_id:
        raise RepositoryConflictError("outcome belongs to a different action")
    if commit.outcome.trace_order != commit.next_step_no:
        raise RepositoryConflictError("outcome order must match next run step")
    expected_status = "succeeded" if commit.outcome.success else "failed"
    if commit.action_status != expected_status:
        raise RepositoryConflictError("terminal action status contradicts its outcome")
    if commit.checkpoint.experiment_run_id != commit.run_id:
        raise RepositoryConflictError("checkpoint belongs to a different run")
    if commit.checkpoint.step_no != commit.next_step_no:
        raise RepositoryConflictError("checkpoint step must match next run step")
    if commit.checkpoint.last_action_id != commit.action_id:
        raise RepositoryConflictError("checkpoint must reference the completed action")
    if commit.checkpoint.pending_action_id is not None:
        raise RepositoryConflictError("terminal checkpoint cannot retain a pending action")
    if commit.audit_event.experiment_run_id != commit.run_id:
        raise RepositoryConflictError("audit event belongs to a different run")
    if commit.audit_event.target_id != commit.outcome.id:
        raise RepositoryConflictError("audit event must target the committed outcome")
    if commit.audit_event.sequence_no != commit.outcome.trace_order:
        raise RepositoryConflictError("audit order must match the committed outcome")
    state = commit.checkpoint.agent_state
    if state.get("current_step") != commit.next_step_no:
        raise RepositoryConflictError("checkpoint state has the wrong current step")
    if state.get("pending_action_id") is not None:
        raise RepositoryConflictError("checkpoint state retained a pending action")
    completed = state.get("completed_action_ids")
    if not isinstance(completed, list) or str(commit.action_id) not in completed:
        raise RepositoryConflictError("checkpoint state lacks the completed action")


def run_with_serialization_retry[T](
    operation: Callable[[], T],
    *,
    max_attempts: int = 3,
    sleeper: Callable[[float], None] = sleep,
    base_delay_seconds: float = 0.05,
) -> T:
    """Retry a complete transaction only for CockroachDB SQLSTATE 40001."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    for attempt in range(max_attempts):
        try:
            return operation()
        except Exception as error:
            retryable = getattr(error, "sqlstate", None) == "40001"
            if not retryable or attempt + 1 == max_attempts:
                raise
            delay = min(base_delay_seconds * (2**attempt), 0.5)
            sleeper(delay)
    raise AssertionError("retry loop exited without returning or raising")
