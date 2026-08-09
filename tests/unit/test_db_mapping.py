from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.app.db.mapping import DEFAULT_SEED_LAB_ID, build_hero_seed, map_trace
from backend.app.db.repository import TraceValidationError
from backend.app.devices.scenarios import run_scenario_a, run_scenario_b
from backend.app.models.trace import AttemptedAction, Outcome, ScenarioTrace

RUN_ID = UUID("8cdfb8a0-245b-4df3-a831-dde31057736b")
BASE_TIME = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def _map(trace: ScenarioTrace):  # type: ignore[no-untyped-def]
    return map_trace(
        trace,
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=RUN_ID,
        base_time=BASE_TIME,
    )


def test_scenario_a_preserves_two_connects_and_failed_evidence() -> None:
    trace = run_scenario_a()
    rows = _map(trace)

    connect_actions = [action for action in rows.actions if action.action_type == "connect"]
    assert len(connect_actions) == 2
    assert connect_actions[0].id != connect_actions[1].id
    failed = [outcome for outcome in rows.outcomes if not outcome.success]
    assert len(failed) == 1
    assert failed[0].error_code == "STALE_RESOURCE"
    assert rows.checkpoint.agent_state["device_states"]["scope_01"]["active_faults"] == []  # type: ignore[index]


def test_scenario_b_keeps_action_device_and_quality_delta() -> None:
    rows = _map(run_scenario_b())
    devices = {device.id: device.name for device in rows.devices}
    intervention = next(
        action for action in rows.actions if action.action_type == "reduce_drive_10_percent"
    )
    outcome = next(row for row in rows.outcomes if row.action_id == intervention.id)

    assert devices[intervention.device_id] == "signal_source_01"
    assert outcome.quality_delta is not None
    assert outcome.quality_delta > 0


def test_mapper_creates_global_timeline_in_original_order() -> None:
    trace = run_scenario_a()
    rows = _map(trace)

    assert [event.sequence_no for event in rows.audit_events] == list(
        range(1, len(trace.ordered_records()) + 1)
    )
    expected_types = {
        "observation": "observed",
        "attempted_action": "action_attempted",
        "outcome": "outcome_recorded",
    }
    assert [event.event_type for event in rows.audit_events] == [
        expected_types[str(record["record_type"])] for record in trace.ordered_records()
    ]


def test_mapper_defensively_copies_mutable_trace_payloads() -> None:
    trace = run_scenario_a()
    rows = _map(trace)
    original = rows.observations[0].payload["resource_hint_status"]

    trace.observations[0].payload["resource_hint_status"] = "mutated"

    assert rows.observations[0].payload["resource_hint_status"] == original


def test_mapper_uses_and_copies_explicit_checkpoint_state() -> None:
    trace = run_scenario_b()
    rows = _map(trace)
    checkpoint_devices = rows.checkpoint.agent_state["device_states"]

    trace.checkpoint_state["devices"]["scope_01"]["connection_state"] = "mutated"  # type: ignore[index]

    assert checkpoint_devices["scope_01"]["connection_state"] == "connected"  # type: ignore[index]
    assert rows.checkpoint.agent_state["physical_state"]["drive_amplitude"] == 0.9  # type: ignore[index]
    assert len(str(rows.run.context["trace_fingerprint"])) == 64
    assert len(str(rows.run.context["persistence_fingerprint"])) == 64


def test_mapper_rejects_contradictory_checkpoint_resource_state() -> None:
    trace = run_scenario_a()
    checkpoint_state = deepcopy(trace.checkpoint_state)
    checkpoint_state["devices"]["scope_01"]["connection_state"] = "fault"  # type: ignore[index]
    invalid = replace(trace, checkpoint_state=checkpoint_state)

    with pytest.raises(TraceValidationError, match="retained a resource"):
        _map(invalid)


@pytest.mark.parametrize("invalid_kind", ["duplicate", "orphan", "unknown_device"])
def test_mapper_rejects_invalid_trace_before_writing(invalid_kind: str) -> None:
    trace = run_scenario_a()
    if invalid_kind == "duplicate":
        actions = (
            replace(trace.attempted_actions[0], order=trace.observations[0].order),
            *trace.attempted_actions[1:],
        )
        invalid = replace(trace, attempted_actions=actions)
    elif invalid_kind == "orphan":
        outcomes = (replace(trace.outcomes[0], action_order=999), *trace.outcomes[1:])
        invalid = replace(trace, outcomes=outcomes)
    else:
        actions = (
            replace(trace.attempted_actions[0], device_id="unknown_01"),
            *trace.attempted_actions[1:],
        )
        invalid = replace(trace, attempted_actions=actions)

    with pytest.raises(TraceValidationError):
        _map(invalid)


def test_mapper_rejects_success_with_error() -> None:
    trace = run_scenario_a()
    failed = trace.outcomes[0]
    invalid_outcome = Outcome(
        order=failed.order,
        device_id=failed.device_id,
        action_order=failed.action_order,
        success=True,
        result={},
        error=failed.error,
    )
    invalid = replace(trace, outcomes=(invalid_outcome, *trace.outcomes[1:]))

    with pytest.raises(TraceValidationError, match="successful outcome"):
        _map(invalid)


def test_mapper_rejects_action_without_outcome() -> None:
    trace = run_scenario_a()
    extra_action = AttemptedAction(
        order=len(trace.ordered_records()) + 1,
        device_id="scope_01",
        action_type="self_test",
        parameters={},
    )
    invalid = replace(trace, attempted_actions=(*trace.attempted_actions, extra_action))

    with pytest.raises(TraceValidationError, match="exactly one"):
        _map(invalid)


def test_hero_seed_contains_connection_anomaly_and_calibration_history() -> None:
    seed = build_hero_seed()

    assert len(seed.traces) == 2
    assert any(memory.memory_type == "connection_recovery" for memory in seed.memories)
    assert any(memory.memory_type == "intervention_result" for memory in seed.memories)
    calibrations = {record.version: record for record in seed.calibrations}
    assert calibrations["v1"].status == "superseded"
    assert calibrations["v1"].parameters["gain"] == 4.2
    assert calibrations["v1"].superseded_by == calibrations["v2"].id
    assert calibrations["v2"].status == "active"
    assert calibrations["v2"].parameters["gain"] == 3.8
    connection_memory = next(
        memory for memory in seed.memories if memory.memory_type == "connection_recovery"
    )
    assert connection_memory.source_observation_id is not None
