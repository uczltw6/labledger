"""Copy-on-write local fake with the same atomic semantics as the SQL repository."""

from copy import deepcopy
from dataclasses import dataclass, field, replace
from uuid import UUID

from backend.app.db.repository import (
    RepositoryConflictError,
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
    MemoryRecord,
    ObservationRecord,
    OutcomeRecord,
    RunRestore,
    StagedAction,
    TimelineRecord,
    TraceRows,
)


class InjectedTransactionFailure(RuntimeError):
    """Test-only failure raised before the fake swaps its committed state."""


@dataclass(slots=True)
class _FakeState:
    devices: dict[UUID, DeviceRecord] = field(default_factory=dict)
    runs: dict[UUID, ExperimentRunRecord] = field(default_factory=dict)
    observations: dict[UUID, ObservationRecord] = field(default_factory=dict)
    actions: dict[UUID, ActionRecord] = field(default_factory=dict)
    outcomes: dict[UUID, OutcomeRecord] = field(default_factory=dict)
    checkpoints: dict[UUID, CheckpointRecord] = field(default_factory=dict)
    audits: dict[UUID, AuditEventRecord] = field(default_factory=dict)
    calibrations: dict[UUID, CalibrationRecord] = field(default_factory=dict)
    memories: dict[UUID, MemoryRecord] = field(default_factory=dict)


class FakeStructuredMemoryRepository:
    """In-memory repository for local tests; it cannot satisfy Gate P2."""

    def __init__(self) -> None:
        self._state = _FakeState()
        self.fail_at: str | None = None

    def _maybe_fail(self, point: str) -> None:
        if self.fail_at == point:
            raise InjectedTransactionFailure(point)

    @staticmethod
    def _apply_trace(state: _FakeState, rows: TraceRows) -> None:
        existing_run = state.runs.get(rows.run.id)
        if existing_run is not None:
            same_trace = (
                existing_run == rows.run
                and all(state.observations.get(row.id) == row for row in rows.observations)
                and all(state.actions.get(row.id) == row for row in rows.actions)
                and all(state.outcomes.get(row.id) == row for row in rows.outcomes)
                and state.checkpoints.get(rows.checkpoint.id) == rows.checkpoint
                and all(state.audits.get(row.id) == row for row in rows.audit_events)
            )
            if not same_trace:
                raise RepositoryConflictError("run ID already contains different trace evidence")
            return
        for device in rows.devices:
            state.devices[device.id] = deepcopy(device)
        state.runs[rows.run.id] = deepcopy(rows.run)
        for observation in rows.observations:
            state.observations[observation.id] = deepcopy(observation)
        for action in rows.actions:
            state.actions[action.id] = deepcopy(action)
        for outcome in rows.outcomes:
            state.outcomes[outcome.id] = deepcopy(outcome)
        state.checkpoints[rows.checkpoint.id] = deepcopy(rows.checkpoint)
        for audit in rows.audit_events:
            state.audits[audit.id] = deepcopy(audit)

    def save_trace(self, rows: TraceRows) -> None:
        state = deepcopy(self._state)
        self._apply_trace(state, rows)
        self._state = state

    def save_hero_seed(self, seed: HeroSeed) -> None:
        state = deepcopy(self._state)
        for trace in seed.traces:
            self._apply_trace(state, trace)
        for calibration in seed.calibrations:
            state.calibrations[calibration.id] = deepcopy(calibration)
        for memory in seed.memories:
            state.memories[memory.id] = deepcopy(memory)
        active_calibration = state.calibrations.get(seed.active_calibration_id)
        if (
            active_calibration is None
            or active_calibration.device_id != seed.active_calibration_device_id
            or active_calibration.status != "active"
        ):
            raise RepositoryConflictError("active calibration does not belong to the target device")
        device = state.devices[seed.active_calibration_device_id]
        state.devices[device.id] = replace(device, active_calibration_id=seed.active_calibration_id)
        self._state = state

    def stage_action(self, staged: StagedAction) -> None:
        validate_staged_action(staged)
        state = deepcopy(self._state)
        for device in staged.devices:
            state.devices[device.id] = deepcopy(device)
        state.runs[staged.run.id] = deepcopy(staged.run)
        state.actions[staged.action.id] = deepcopy(staged.action)
        state.checkpoints[staged.checkpoint.id] = deepcopy(staged.checkpoint)
        state.audits[staged.audit_event.id] = deepcopy(staged.audit_event)
        self._state = state

    def commit_action_step(self, commit: ActionStepCommit) -> None:
        validate_action_step_commit(commit)
        state = deepcopy(self._state)
        run = state.runs.get(commit.run_id)
        action = state.actions.get(commit.action_id)
        if run is None or action is None:
            raise RepositoryConflictError("run or action does not exist")
        if action.experiment_run_id != commit.run_id:
            raise RepositoryConflictError("action belongs to a different run")
        if action.status not in {"proposed", "running"}:
            raise RepositoryConflictError("action is already terminal")
        if run.current_step != commit.expected_step_no:
            raise RepositoryConflictError("run progress changed before commit")
        if any(outcome.action_id == commit.action_id for outcome in state.outcomes.values()):
            raise RepositoryConflictError("action already has an outcome")
        if any(
            checkpoint.experiment_run_id == commit.run_id
            and checkpoint.step_no == commit.next_step_no
            for checkpoint in state.checkpoints.values()
        ):
            raise RepositoryConflictError("checkpoint step already exists")

        state.actions[action.id] = replace(
            action,
            status=commit.action_status,
            executed_at=commit.executed_at,
        )
        self._maybe_fail("after_action_update")
        state.outcomes[commit.outcome.id] = deepcopy(commit.outcome)
        self._maybe_fail("after_outcome_insert")
        state.runs[run.id] = replace(
            run,
            status=commit.run_status,
            current_step=commit.next_step_no,
            context=deepcopy(commit.run_context),
            ended_at=commit.executed_at if commit.run_status == "completed" else run.ended_at,
        )
        self._maybe_fail("after_run_update")
        state.checkpoints[commit.checkpoint.id] = deepcopy(commit.checkpoint)
        self._maybe_fail("after_checkpoint_insert_before_commit")
        state.audits[commit.audit_event.id] = deepcopy(commit.audit_event)
        self._state = state

    def load_run(self, run_id: UUID) -> ExperimentRunRecord | None:
        record = self._state.runs.get(run_id)
        return None if record is None else deepcopy(record)

    def load_latest_checkpoint(self, run_id: UUID) -> CheckpointRecord | None:
        matches = [
            checkpoint
            for checkpoint in self._state.checkpoints.values()
            if checkpoint.experiment_run_id == run_id
        ]
        if not matches:
            return None
        return deepcopy(max(matches, key=lambda row: (row.step_no, row.created_at, row.id)))

    def load_timeline(self, run_id: UUID) -> tuple[TimelineRecord, ...]:
        audits = sorted(
            (event for event in self._state.audits.values() if event.experiment_run_id == run_id),
            key=lambda event: event.sequence_no,
        )
        return tuple(
            TimelineRecord(
                sequence_no=event.sequence_no,
                event_type=event.event_type,
                target_type=event.target_type,
                target_id=event.target_id,
                detail=deepcopy(event.detail),
            )
            for event in audits
        )

    def load_run_restore(self, run_id: UUID) -> RunRestore | None:
        run = self.load_run(run_id)
        checkpoint = self.load_latest_checkpoint(run_id)
        if run is None or checkpoint is None:
            return None
        action_ids = {
            action.id
            for action in self._state.actions.values()
            if action.experiment_run_id == run_id
        }
        outcome_count = sum(
            outcome.action_id in action_ids for outcome in self._state.outcomes.values()
        )
        return RunRestore(
            run=run,
            checkpoint=checkpoint,
            timeline=self.load_timeline(run_id),
            action_count=len(action_ids),
            outcome_count=outcome_count,
        )
