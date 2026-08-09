"""Map validated P1 simulator traces to stable structured-memory rows."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid5

from backend.app.db.repository import TraceValidationError
from backend.app.db.types import (
    ActionRecord,
    AuditEventRecord,
    CalibrationRecord,
    CheckpointRecord,
    DeviceRecord,
    ExperimentRunRecord,
    HeroSeed,
    MemoryRecord,
    ObservationRecord,
    OutcomeRecord,
    TraceRows,
)
from backend.app.devices.scenarios import run_scenario_a, run_scenario_b
from backend.app.models.trace import JSONValue, ScenarioTrace

DEVICE_CATALOG: dict[str, tuple[str, str, str]] = {
    "signal_source_01": ("signal_source", "Synthetic Instruments", "SS-100"),
    "scope_01": ("oscilloscope", "Synthetic Instruments", "SCOPE-200"),
    "mux_01": ("multiplexer", "Synthetic Instruments", "MUX-8"),
    "temperature_01": ("temperature_sensor", "Synthetic Instruments", "TEMP-1"),
}

DEFAULT_SEED_LAB_ID = UUID("d7a81cd4-0ec8-4e56-b2e3-cf61df5d01d5")
DEFAULT_SEED_TIME = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _clone_object(value: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return cast(dict[str, JSONValue], json.loads(json.dumps(value, sort_keys=True)))


def _record_time(base_time: datetime, order: int) -> datetime:
    return base_time + timedelta(microseconds=order)


def _validate_trace(trace: ScenarioTrace) -> None:
    orders = [observation.order for observation in trace.observations]
    orders.extend(action.order for action in trace.attempted_actions)
    orders.extend(outcome.order for outcome in trace.outcomes)
    if not orders or any(order <= 0 for order in orders):
        raise TraceValidationError("trace orders must be positive")
    if len(orders) != len(set(orders)):
        raise TraceValidationError("trace orders must be globally unique")
    if sorted(orders) != list(range(1, len(orders) + 1)):
        raise TraceValidationError("trace orders must be contiguous from one")

    known_devices = set(DEVICE_CATALOG)
    used_devices = {observation.device_id for observation in trace.observations}
    used_devices.update(action.device_id for action in trace.attempted_actions)
    used_devices.update(outcome.device_id for outcome in trace.outcomes)
    unknown_devices = sorted(used_devices - known_devices)
    if unknown_devices:
        raise TraceValidationError(f"unknown logical device: {unknown_devices[0]}")

    actions_by_order = {action.order: action for action in trace.attempted_actions}
    outcome_action_orders = [outcome.action_order for outcome in trace.outcomes]
    if len(outcome_action_orders) != len(set(outcome_action_orders)):
        raise TraceValidationError("each action may have at most one outcome")
    if set(outcome_action_orders) != set(actions_by_order):
        raise TraceValidationError("every action must have exactly one linked outcome")
    for outcome in trace.outcomes:
        action = actions_by_order.get(outcome.action_order)
        if action is None:
            raise TraceValidationError("outcome references an unknown action order")
        if outcome.device_id != action.device_id:
            raise TraceValidationError("outcome device must match its action device")
        if outcome.success and outcome.error is not None:
            raise TraceValidationError("a successful outcome cannot contain an error")


def _checkpoint_snapshot(
    trace: ScenarioTrace,
) -> tuple[dict[str, str], dict[str, list[JSONValue]], dict[str, JSONValue]]:
    snapshot = _clone_object(trace.checkpoint_state)
    raw_devices = snapshot.get("devices")
    physical_state = snapshot.get("physical_state")
    if not isinstance(raw_devices, dict) or not isinstance(physical_state, dict):
        raise TraceValidationError("trace checkpoint must contain device and physical state")
    if set(raw_devices) != set(DEVICE_CATALOG):
        raise TraceValidationError(
            "trace checkpoint must contain exactly the four simulator devices"
        )

    states: dict[str, str] = {}
    active_faults: dict[str, list[JSONValue]] = {}
    for device_id, raw_state in raw_devices.items():
        if not isinstance(raw_state, dict):
            raise TraceValidationError("checkpoint device state must be an object")
        connection_state = raw_state.get("connection_state")
        if connection_state not in {"disconnected", "connected", "fault"}:
            raise TraceValidationError("checkpoint contains an invalid connection state")
        connected_resource = raw_state.get("connected_resource")
        if connection_state != "connected" and connected_resource is not None:
            raise TraceValidationError("non-connected checkpoint state retained a resource")
        raw_faults = raw_state.get("active_faults")
        if not isinstance(raw_faults, list) or not all(
            isinstance(fault, str) for fault in raw_faults
        ):
            raise TraceValidationError("checkpoint active faults must be a string list")
        states[device_id] = cast(str, connection_state)
        active_faults[device_id] = list(raw_faults)
    return states, active_faults, snapshot


def _quality_delta(result: dict[str, JSONValue]) -> float | None:
    before = result.get("before_signal_quality")
    after = result.get("after_signal_quality")
    if (
        isinstance(before, (int, float))
        and not isinstance(before, bool)
        and isinstance(after, (int, float))
        and not isinstance(after, bool)
    ):
        return float(after) - float(before)
    return None


def map_trace(
    trace: ScenarioTrace,
    *,
    lab_id: UUID,
    run_id: UUID,
    base_time: datetime,
) -> TraceRows:
    """Validate and map a complete trace without retaining mutable JSON aliases."""

    _validate_trace(trace)
    if base_time.tzinfo is None:
        raise ValueError("base_time must be timezone-aware")

    states, fault_state, checkpoint_snapshot = _checkpoint_snapshot(trace)
    device_ids = {name: uuid5(lab_id, f"device:{name}") for name in DEVICE_CATALOG}
    devices = tuple(
        DeviceRecord(
            id=device_ids[name],
            lab_id=lab_id,
            name=name,
            device_type=details[0],
            vendor=details[1],
            model=details[2],
            resource_hint=f"SIM::{name}",
            connection_state=states[name],
            metadata={"synthetic": True, "active_faults": list(fault_state[name])},
            created_at=base_time,
            updated_at=_record_time(base_time, len(trace.ordered_records())),
        )
        for name, details in DEVICE_CATALOG.items()
    )

    outcomes_by_action = {outcome.action_order: outcome for outcome in trace.outcomes}
    action_ids = {
        action.order: uuid5(run_id, f"action:{action.order}") for action in trace.attempted_actions
    }
    max_order = len(trace.ordered_records())
    trace_fingerprint = hashlib.sha256(trace.to_json().encode("utf-8")).hexdigest()
    persistence_material = (
        f"{trace_fingerprint}|{lab_id}|{run_id}|{base_time.isoformat()}|mapping-version:2"
    )
    persistence_fingerprint = hashlib.sha256(persistence_material.encode("utf-8")).hexdigest()
    run = ExperimentRunRecord(
        id=run_id,
        name=trace.scenario_id,
        status="completed",
        recipe_version=f"p1:{trace.scenario_id}",
        started_at=base_time,
        ended_at=_record_time(base_time, max_order),
        current_step=max_order,
        context={
            "synthetic": True,
            "scenario_id": trace.scenario_id,
            "seed": trace.seed,
            "trace_record_count": max_order,
            "trace_fingerprint": trace_fingerprint,
            "persistence_fingerprint": persistence_fingerprint,
            "mapping_version": 2,
        },
        created_by="labledger-p2-seed",
    )

    observations = tuple(
        ObservationRecord(
            id=uuid5(run_id, f"observation:{observation.order}"),
            experiment_run_id=run_id,
            device_id=device_ids[observation.device_id],
            trace_order=observation.order,
            observation_type=observation.observation_type,
            payload=_clone_object(observation.payload),
            summary=observation.observation_type.replace("_", " "),
            severity=(
                "warning"
                if "fault_id" in observation.payload or "fault_ids" in observation.payload
                else "info"
            ),
            observed_at=_record_time(base_time, observation.order),
            provenance={
                "synthetic": True,
                "scenario_id": trace.scenario_id,
                "seed": trace.seed,
                "trace_order": observation.order,
            },
        )
        for observation in trace.observations
    )
    actions = tuple(
        ActionRecord(
            id=action_ids[action.order],
            experiment_run_id=run_id,
            device_id=device_ids[action.device_id],
            trace_order=action.order,
            action_type=action.action_type,
            parameters=_clone_object(action.parameters),
            risk_level="low",
            approval_state="not_required",
            selected_reason="deterministic P1 baseline",
            memory_ids=(),
            status="succeeded" if outcomes_by_action[action.order].success else "failed",
            created_at=_record_time(base_time, action.order),
            executed_at=_record_time(base_time, outcomes_by_action[action.order].order),
        )
        for action in trace.attempted_actions
    )
    outcomes = tuple(
        OutcomeRecord(
            id=uuid5(run_id, f"outcome:{outcome.order}"),
            action_id=action_ids[outcome.action_order],
            trace_order=outcome.order,
            success=outcome.success,
            result=_clone_object(outcome.result),
            quality_delta=_quality_delta(outcome.result),
            error_code=None if outcome.error is None else outcome.error.code,
            summary=(
                "action succeeded"
                if outcome.success
                else (
                    "action failed"
                    if outcome.error is None
                    else f"action failed: {outcome.error.message}"
                )
            ),
            observed_at=_record_time(base_time, outcome.order),
        )
        for outcome in trace.outcomes
    )

    action_by_order = {action.trace_order: action for action in actions}
    observation_by_order = {observation.trace_order: observation for observation in observations}
    outcome_by_order = {outcome.trace_order: outcome for outcome in outcomes}
    audit_events: list[AuditEventRecord] = []
    for order in range(1, max_order + 1):
        if order in observation_by_order:
            observation_record = observation_by_order[order]
            event_type, target_type, target_id = (
                "observed",
                "observation",
                observation_record.id,
            )
            detail: dict[str, JSONValue] = {
                "trace_order": order,
                "observation_type": observation_record.observation_type,
                "payload": _clone_object(observation_record.payload),
            }
        elif order in action_by_order:
            action_record = action_by_order[order]
            event_type, target_type, target_id = (
                "action_attempted",
                "action",
                action_record.id,
            )
            detail = {
                "trace_order": order,
                "action_type": action_record.action_type,
                "parameters": _clone_object(action_record.parameters),
            }
        else:
            outcome_record = outcome_by_order[order]
            event_type, target_type, target_id = (
                "outcome_recorded",
                "outcome",
                outcome_record.id,
            )
            detail = {
                "trace_order": order,
                "success": outcome_record.success,
                "error_code": outcome_record.error_code,
                "result": _clone_object(outcome_record.result),
            }
        audit_events.append(
            AuditEventRecord(
                id=uuid5(run_id, f"audit:{order}"),
                experiment_run_id=run_id,
                sequence_no=order,
                actor_type="simulator",
                actor_id="p1-deterministic-scenario",
                event_type=event_type,
                target_type=target_type,
                target_id=target_id,
                detail=detail,
                created_at=_record_time(base_time, order),
            )
        )

    completed_action_ids: list[JSONValue] = [str(action.id) for action in actions]
    last_action_id = max(actions, key=lambda action: action.trace_order).id if actions else None
    checkpoint = CheckpointRecord(
        id=uuid5(run_id, f"checkpoint:{max_order}"),
        experiment_run_id=run_id,
        step_no=max_order,
        agent_state={
            "schema_version": 1,
            "synthetic": True,
            "scenario_id": trace.scenario_id,
            "seed": trace.seed,
            "run_status": "completed",
            "current_step": max_order,
            "next_step": max_order + 1,
            "device_states": _clone_object(
                cast(dict[str, JSONValue], checkpoint_snapshot["devices"])
            ),
            "physical_state": _clone_object(
                cast(dict[str, JSONValue], checkpoint_snapshot["physical_state"])
            ),
            "completed_action_ids": completed_action_ids,
            "pending_action_id": None,
        },
        last_action_id=last_action_id,
        pending_action_id=None,
        created_at=_record_time(base_time, max_order + 1),
    )
    return TraceRows(
        devices=devices,
        run=run,
        observations=observations,
        actions=actions,
        outcomes=outcomes,
        checkpoint=checkpoint,
        audit_events=tuple(audit_events),
    )


def build_hero_seed(
    *,
    lab_id: UUID = DEFAULT_SEED_LAB_ID,
    base_time: datetime = DEFAULT_SEED_TIME,
) -> HeroSeed:
    """Build structured Scenario A/B evidence plus superseded/active calibration facts."""

    trace_a = run_scenario_a()
    trace_b = run_scenario_b()
    rows_a = map_trace(
        trace_a,
        lab_id=lab_id,
        run_id=uuid5(lab_id, f"run:{trace_a.scenario_id}:{trace_a.seed}"),
        base_time=base_time,
    )
    rows_b = map_trace(
        trace_b,
        lab_id=lab_id,
        run_id=uuid5(lab_id, f"run:{trace_b.scenario_id}:{trace_b.seed}"),
        base_time=base_time + timedelta(hours=1),
    )
    scope_id = uuid5(lab_id, "device:scope_01")
    calibration_v1_id = uuid5(scope_id, "calibration:v1")
    calibration_v2_id = uuid5(scope_id, "calibration:v2")
    calibration_v2 = CalibrationRecord(
        id=calibration_v2_id,
        device_id=scope_id,
        version="v2",
        parameters={"gain": 3.8},
        status="active",
        valid_from=base_time + timedelta(days=1),
        valid_until=None,
        superseded_by=None,
        confidence=1.0,
        provenance={"synthetic": True, "source": "hero-scenario-c"},
    )
    calibration_v1 = CalibrationRecord(
        id=calibration_v1_id,
        device_id=scope_id,
        version="v1",
        parameters={"gain": 4.2},
        status="superseded",
        valid_from=base_time,
        valid_until=calibration_v2.valid_from,
        superseded_by=calibration_v2_id,
        confidence=1.0,
        provenance={"synthetic": True, "source": "hero-scenario-c"},
    )

    recovery_action = next(
        action
        for action in rows_a.actions
        if action.action_type == "connect" and action.status == "succeeded"
    )
    recovery_outcome = next(
        outcome for outcome in rows_a.outcomes if outcome.action_id == recovery_action.id
    )
    connection_observation = next(
        observation
        for observation in rows_a.observations
        if observation.observation_type == "connection_state"
    )
    anomaly_observation = next(
        observation
        for observation in rows_b.observations
        if observation.observation_type == "experimental_anomaly"
    )
    intervention_action = next(
        action for action in rows_b.actions if action.action_type == "reduce_drive_10_percent"
    )
    intervention_outcome = next(
        outcome for outcome in rows_b.outcomes if outcome.action_id == intervention_action.id
    )
    memory_v1_id = uuid5(calibration_v1_id, "memory")
    memory_v2_id = uuid5(calibration_v2_id, "memory")
    memories = (
        MemoryRecord(
            id=uuid5(rows_a.run.id, "memory:connection-recovery"),
            lab_id=lab_id,
            experiment_run_id=rows_a.run.id,
            device_id=scope_id,
            memory_type="connection_recovery",
            title="Rediscovery recovered a stale scope resource",
            content=(
                "A stale resource failed; rediscovery, reconnect, and identity validation "
                "succeeded."
            ),
            embedding_text="scope stale resource rediscover reconnect validate identity recovery",
            status="active",
            confidence=1.0,
            valid_from=rows_a.run.started_at or base_time,
            valid_until=None,
            superseded_by=None,
            source_observation_id=connection_observation.id,
            source_action_id=recovery_action.id,
            source_outcome_id=recovery_outcome.id,
            provenance={"synthetic": True, "scenario_id": rows_a.run.name},
            created_at=rows_a.run.ended_at or base_time,
        ),
        MemoryRecord(
            id=uuid5(rows_b.run.id, "memory:intervention-result"),
            lab_id=lab_id,
            experiment_run_id=rows_b.run.id,
            device_id=uuid5(lab_id, "device:signal_source_01"),
            memory_type="intervention_result",
            title="Drive reduction restored signal quality",
            content=(
                "Calibration A failed; reducing drive amplitude by ten percent improved noise "
                "and quality."
            ),
            embedding_text=(
                "high temperature rising noise falling signal calibration failed reduce drive "
                "success"
            ),
            status="active",
            confidence=1.0,
            valid_from=rows_b.run.started_at or base_time,
            valid_until=None,
            superseded_by=None,
            source_observation_id=anomaly_observation.id,
            source_action_id=intervention_action.id,
            source_outcome_id=intervention_outcome.id,
            provenance={"synthetic": True, "scenario_id": rows_b.run.name},
            created_at=rows_b.run.ended_at or base_time,
        ),
        MemoryRecord(
            id=memory_v1_id,
            lab_id=lab_id,
            experiment_run_id=None,
            device_id=scope_id,
            memory_type="calibration_fact",
            title="Scope calibration v1",
            content="Calibration v1 gain 4.2 is retained as superseded history.",
            embedding_text="scope calibration v1 gain 4.2 superseded",
            status="superseded",
            confidence=1.0,
            valid_from=calibration_v1.valid_from,
            valid_until=calibration_v1.valid_until,
            superseded_by=memory_v2_id,
            source_observation_id=None,
            source_action_id=None,
            source_outcome_id=None,
            provenance={"synthetic": True, "calibration_id": str(calibration_v1_id)},
            created_at=calibration_v1.valid_from,
        ),
        MemoryRecord(
            id=memory_v2_id,
            lab_id=lab_id,
            experiment_run_id=None,
            device_id=scope_id,
            memory_type="calibration_fact",
            title="Scope calibration v2",
            content="Calibration v2 gain 3.8 is the active calibration.",
            embedding_text="scope calibration v2 gain 3.8 active",
            status="active",
            confidence=1.0,
            valid_from=calibration_v2.valid_from,
            valid_until=None,
            superseded_by=None,
            source_observation_id=None,
            source_action_id=None,
            source_outcome_id=None,
            provenance={"synthetic": True, "calibration_id": str(calibration_v2_id)},
            created_at=calibration_v2.valid_from,
        ),
    )
    return HeroSeed(
        traces=(rows_a, rows_b),
        calibrations=(calibration_v2, calibration_v1),
        memories=memories,
        active_calibration_device_id=scope_id,
        active_calibration_id=calibration_v2_id,
    )
