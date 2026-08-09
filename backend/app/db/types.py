"""Typed records shared by real and fake structured-memory repositories."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from backend.app.models.trace import JSONValue

type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    id: UUID
    lab_id: UUID
    name: str
    device_type: str
    vendor: str | None
    model: str | None
    resource_hint: str | None
    connection_state: str
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime
    active_calibration_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ExperimentRunRecord:
    id: UUID
    name: str
    status: str
    recipe_version: str
    started_at: datetime | None
    ended_at: datetime | None
    current_step: int
    context: JSONObject
    created_by: str


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    id: UUID
    experiment_run_id: UUID
    device_id: UUID
    trace_order: int
    observation_type: str
    payload: JSONObject
    summary: str
    severity: str
    observed_at: datetime
    provenance: JSONObject


@dataclass(frozen=True, slots=True)
class ActionRecord:
    id: UUID
    experiment_run_id: UUID
    device_id: UUID
    trace_order: int
    action_type: str
    parameters: JSONObject
    risk_level: str
    approval_state: str
    selected_reason: str
    memory_ids: tuple[UUID, ...]
    status: str
    created_at: datetime
    executed_at: datetime | None


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    id: UUID
    action_id: UUID
    trace_order: int
    success: bool
    result: JSONObject
    quality_delta: float | None
    error_code: str | None
    summary: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    id: UUID
    experiment_run_id: UUID
    step_no: int
    agent_state: JSONObject
    last_action_id: UUID | None
    pending_action_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEventRecord:
    id: UUID
    experiment_run_id: UUID
    sequence_no: int
    actor_type: str
    actor_id: str
    event_type: str
    target_type: str
    target_id: UUID | None
    detail: JSONObject
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CalibrationRecord:
    id: UUID
    device_id: UUID
    version: str
    parameters: JSONObject
    status: str
    valid_from: datetime
    valid_until: datetime | None
    superseded_by: UUID | None
    confidence: float
    provenance: JSONObject


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: UUID
    lab_id: UUID
    experiment_run_id: UUID | None
    device_id: UUID | None
    memory_type: str
    title: str
    content: str
    embedding_text: str
    status: str
    confidence: float
    valid_from: datetime
    valid_until: datetime | None
    superseded_by: UUID | None
    source_observation_id: UUID | None
    source_action_id: UUID | None
    source_outcome_id: UUID | None
    provenance: JSONObject
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TraceRows:
    devices: tuple[DeviceRecord, ...]
    run: ExperimentRunRecord
    observations: tuple[ObservationRecord, ...]
    actions: tuple[ActionRecord, ...]
    outcomes: tuple[OutcomeRecord, ...]
    checkpoint: CheckpointRecord
    audit_events: tuple[AuditEventRecord, ...]


@dataclass(frozen=True, slots=True)
class HeroSeed:
    traces: tuple[TraceRows, ...]
    calibrations: tuple[CalibrationRecord, ...]
    memories: tuple[MemoryRecord, ...]
    active_calibration_device_id: UUID
    active_calibration_id: UUID


@dataclass(frozen=True, slots=True)
class StagedAction:
    devices: tuple[DeviceRecord, ...]
    run: ExperimentRunRecord
    action: ActionRecord
    checkpoint: CheckpointRecord
    audit_event: AuditEventRecord


@dataclass(frozen=True, slots=True)
class ActionStepCommit:
    run_id: UUID
    action_id: UUID
    expected_step_no: int
    next_step_no: int
    action_status: str
    executed_at: datetime
    outcome: OutcomeRecord
    run_status: str
    run_context: JSONObject
    checkpoint: CheckpointRecord
    audit_event: AuditEventRecord


@dataclass(frozen=True, slots=True)
class TimelineRecord:
    sequence_no: int
    event_type: str
    target_type: str
    target_id: UUID | None
    detail: JSONObject


@dataclass(frozen=True, slots=True)
class RunRestore:
    run: ExperimentRunRecord
    checkpoint: CheckpointRecord
    timeline: tuple[TimelineRecord, ...]
    action_count: int
    outcome_count: int
