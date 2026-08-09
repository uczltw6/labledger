from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import pytest

from backend.app.db.fake import FakeStructuredMemoryRepository, InjectedTransactionFailure
from backend.app.db.mapping import DEFAULT_SEED_LAB_ID, build_hero_seed, map_trace
from backend.app.db.repository import RepositoryConflictError
from backend.app.db.types import (
    ActionRecord,
    ActionStepCommit,
    AuditEventRecord,
    CheckpointRecord,
    ExperimentRunRecord,
    OutcomeRecord,
    StagedAction,
)
from backend.app.devices.scenarios import run_scenario_a

BASE_TIME = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def _staged_write() -> tuple[StagedAction, ActionStepCommit]:
    run_id = uuid4()
    trace_rows = map_trace(
        run_scenario_a(),
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=uuid4(),
        base_time=BASE_TIME,
    )
    scope = next(device for device in trace_rows.devices if device.name == "scope_01")
    action_id = uuid5(run_id, "action:1")
    run = ExperimentRunRecord(
        id=run_id,
        name="atomic-step-test",
        status="running",
        recipe_version="p2-test",
        started_at=BASE_TIME,
        ended_at=None,
        current_step=0,
        context={"synthetic": True},
        created_by="pytest",
    )
    action = ActionRecord(
        id=action_id,
        experiment_run_id=run_id,
        device_id=scope.id,
        trace_order=1,
        action_type="reconnect",
        parameters={},
        risk_level="low",
        approval_state="not_required",
        selected_reason="transaction test",
        memory_ids=(),
        status="proposed",
        created_at=BASE_TIME + timedelta(microseconds=1),
        executed_at=None,
    )
    initial_checkpoint = CheckpointRecord(
        id=uuid5(run_id, "checkpoint:0"),
        experiment_run_id=run_id,
        step_no=0,
        agent_state={
            "current_step": 0,
            "completed_action_ids": [],
            "pending_action_id": str(action_id),
        },
        last_action_id=None,
        pending_action_id=action_id,
        created_at=BASE_TIME,
    )
    staged_audit = AuditEventRecord(
        id=uuid5(run_id, "audit:1"),
        experiment_run_id=run_id,
        sequence_no=1,
        actor_type="simulator",
        actor_id="pytest",
        event_type="action_proposed",
        target_type="action",
        target_id=action_id,
        detail={"trace_order": 1},
        created_at=action.created_at,
    )
    staged = StagedAction(
        devices=(scope,),
        run=run,
        action=action,
        checkpoint=initial_checkpoint,
        audit_event=staged_audit,
    )
    executed_at = BASE_TIME + timedelta(microseconds=2)
    outcome = OutcomeRecord(
        id=uuid5(run_id, "outcome:2"),
        action_id=action_id,
        trace_order=2,
        success=True,
        result={"connected": True},
        quality_delta=None,
        error_code=None,
        summary="reconnect succeeded",
        observed_at=executed_at,
    )
    final_checkpoint = CheckpointRecord(
        id=uuid5(run_id, "checkpoint:2"),
        experiment_run_id=run_id,
        step_no=2,
        agent_state={
            "current_step": 2,
            "next_step": 3,
            "device_states": {"scope_01": {"connection_state": "connected"}},
            "completed_action_ids": [str(action_id)],
            "pending_action_id": None,
        },
        last_action_id=action_id,
        pending_action_id=None,
        created_at=executed_at,
    )
    final_audit = AuditEventRecord(
        id=uuid5(run_id, "audit:2"),
        experiment_run_id=run_id,
        sequence_no=2,
        actor_type="simulator",
        actor_id="pytest",
        event_type="outcome_recorded",
        target_type="outcome",
        target_id=outcome.id,
        detail={"trace_order": 2, "success": True},
        created_at=executed_at,
    )
    commit = ActionStepCommit(
        run_id=run_id,
        action_id=action_id,
        expected_step_no=0,
        next_step_no=2,
        action_status="succeeded",
        executed_at=executed_at,
        outcome=outcome,
        run_status="running",
        run_context={"synthetic": True, "last_action": str(action_id)},
        checkpoint=final_checkpoint,
        audit_event=final_audit,
    )
    return staged, commit


def test_fake_successfully_commits_all_step_state_atomically() -> None:
    staged, commit = _staged_write()
    repository = FakeStructuredMemoryRepository()
    repository.stage_action(staged)

    repository.commit_action_step(commit)

    restored = repository.load_run_restore(staged.run.id)
    assert restored is not None
    assert restored.run.current_step == 2
    assert restored.checkpoint.step_no == 2
    assert restored.checkpoint.pending_action_id is None
    assert restored.action_count == 1
    assert restored.outcome_count == 1
    assert [event.sequence_no for event in restored.timeline] == [1, 2]


@pytest.mark.parametrize(
    "failure_point",
    [
        "after_action_update",
        "after_outcome_insert",
        "after_run_update",
        "after_checkpoint_insert_before_commit",
    ],
)
def test_fake_transaction_failure_never_leaves_partial_state(failure_point: str) -> None:
    staged, commit = _staged_write()
    repository = FakeStructuredMemoryRepository()
    repository.stage_action(staged)
    repository.fail_at = failure_point

    with pytest.raises(InjectedTransactionFailure):
        repository.commit_action_step(commit)

    restored = repository.load_run_restore(staged.run.id)
    assert restored is not None
    assert restored.run.current_step == 0
    assert restored.checkpoint.step_no == 0
    assert restored.checkpoint.pending_action_id == staged.action.id
    assert restored.action_count == 1
    assert restored.outcome_count == 0
    assert [event.sequence_no for event in restored.timeline] == [1]


def test_fake_rejects_stale_progress_without_writes() -> None:
    staged, commit = _staged_write()
    repository = FakeStructuredMemoryRepository()
    repository.stage_action(staged)
    stale = ActionStepCommit(
        run_id=commit.run_id,
        action_id=commit.action_id,
        expected_step_no=1,
        next_step_no=2,
        action_status=commit.action_status,
        executed_at=commit.executed_at,
        outcome=commit.outcome,
        run_status=commit.run_status,
        run_context=commit.run_context,
        checkpoint=commit.checkpoint,
        audit_event=commit.audit_event,
    )

    with pytest.raises(RepositoryConflictError, match="progress"):
        repository.commit_action_step(stale)

    restored = repository.load_run_restore(staged.run.id)
    assert restored is not None
    assert restored.run.current_step == 0
    assert restored.outcome_count == 0


def test_fake_loads_are_defensive_copies() -> None:
    rows = map_trace(
        run_scenario_a(),
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=UUID("8cdfb8a0-245b-4df3-a831-dde31057736b"),
        base_time=BASE_TIME,
    )
    repository = FakeStructuredMemoryRepository()
    repository.save_trace(rows)
    loaded = repository.load_run(rows.run.id)
    assert loaded is not None

    loaded.context["scenario_id"] = "mutated"
    loaded_again = repository.load_run(rows.run.id)

    assert loaded_again is not None
    assert loaded_again.context["scenario_id"] == rows.run.context["scenario_id"]


def test_fake_idempotent_replay_accepts_identical_trace_and_rejects_divergence() -> None:
    run_id = UUID("8cdfb8a0-245b-4df3-a831-dde31057736b")
    first = map_trace(
        run_scenario_a(),
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=run_id,
        base_time=BASE_TIME,
    )
    repository = FakeStructuredMemoryRepository()
    repository.save_trace(first)
    repository.save_trace(first)
    divergent = replace(first, run=replace(first.run, context={"trace_fingerprint": "other"}))

    with pytest.raises(RepositoryConflictError, match="different trace"):
        repository.save_trace(divergent)


def test_fake_rejects_cross_run_pending_checkpoint() -> None:
    staged, _commit = _staged_write()
    invalid = replace(
        staged,
        checkpoint=replace(staged.checkpoint, experiment_run_id=uuid4()),
    )

    with pytest.raises(RepositoryConflictError, match="different run"):
        FakeStructuredMemoryRepository().stage_action(invalid)


def test_fake_rejects_mismatched_commit_audit_target() -> None:
    staged, commit = _staged_write()
    repository = FakeStructuredMemoryRepository()
    repository.stage_action(staged)
    invalid = replace(
        commit,
        audit_event=replace(commit.audit_event, target_id=uuid4()),
    )

    with pytest.raises(RepositoryConflictError, match="target"):
        repository.commit_action_step(invalid)


def test_fake_rejects_active_calibration_from_another_device() -> None:
    seed = build_hero_seed()
    wrong_device = next(
        device.id for device in seed.traces[0].devices if device.name == "signal_source_01"
    )
    invalid = replace(seed, active_calibration_device_id=wrong_device)

    with pytest.raises(RepositoryConflictError, match="does not belong"):
        FakeStructuredMemoryRepository().save_hero_seed(invalid)
