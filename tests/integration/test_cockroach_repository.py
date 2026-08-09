import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4, uuid5

import psycopg
import pytest

from backend.app.db.mapping import DEFAULT_SEED_LAB_ID, map_trace
from backend.app.db.migrations import apply_migration, verify_p2_schema
from backend.app.db.psycopg_repository import PsycopgStructuredMemoryRepository
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
from scripts.verify_p2 import _preflight_database_url

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "001_init.sql"
DATABASE_URL = os.environ.get("COCKROACH_DATABASE_URL")

if DATABASE_URL is not None:
    _preflight_database_url(DATABASE_URL)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="COCKROACH_DATABASE_URL is absent; live P2 evidence is unavailable",
    ),
]


def _url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _staged_action() -> tuple[StagedAction, ActionStepCommit]:
    now = datetime.now(UTC)
    run_id = uuid4()
    mapped = map_trace(
        run_scenario_a(),
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=uuid4(),
        base_time=now,
    )
    scope = next(device for device in mapped.devices if device.name == "scope_01")
    action_id = uuid5(run_id, "action:1")
    run = ExperimentRunRecord(
        id=run_id,
        name="live-atomic-rollback",
        status="running",
        recipe_version="p2-live-test",
        started_at=now,
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
        selected_reason="live rollback test",
        memory_ids=(),
        status="proposed",
        created_at=now + timedelta(microseconds=1),
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
        created_at=now,
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
    staged = StagedAction((scope,), run, action, initial_checkpoint, staged_audit)
    executed_at = now + timedelta(microseconds=2)
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
    colliding_checkpoint = CheckpointRecord(
        id=initial_checkpoint.id,
        experiment_run_id=run_id,
        step_no=2,
        agent_state={"current_step": 2, "completed_action_ids": [str(action_id)]},
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
        run_context={"synthetic": True},
        checkpoint=colliding_checkpoint,
        audit_event=final_audit,
    )
    return staged, commit


def test_live_migration_is_repeatable_and_has_expected_schema() -> None:
    apply_migration(_url(), MIGRATION)
    apply_migration(_url(), MIGRATION)

    assert verify_p2_schema(_url()) == ()


def test_live_trace_persists_and_loads_through_a_new_connection() -> None:
    apply_migration(_url(), MIGRATION)
    trace = run_scenario_a()
    rows = map_trace(
        trace,
        lab_id=DEFAULT_SEED_LAB_ID,
        run_id=uuid4(),
        base_time=datetime.now(UTC),
    )
    PsycopgStructuredMemoryRepository(_url()).save_trace(rows)

    restored = PsycopgStructuredMemoryRepository(_url()).load_run_restore(rows.run.id)

    assert restored is not None
    assert restored.run.current_step == len(trace.ordered_records())
    assert restored.checkpoint.step_no == restored.run.current_step
    assert restored.action_count == len(trace.attempted_actions)
    assert restored.outcome_count == len(trace.outcomes)
    assert any(
        event.event_type == "outcome_recorded" and event.detail["success"] is False
        for event in restored.timeline
    )


def test_live_late_failure_rolls_back_action_outcome_run_and_checkpoint() -> None:
    apply_migration(_url(), MIGRATION)
    staged, commit = _staged_action()
    repository = PsycopgStructuredMemoryRepository(_url())
    repository.stage_action(staged)

    with pytest.raises(psycopg.errors.UniqueViolation):
        repository.commit_action_step(commit)

    restored = PsycopgStructuredMemoryRepository(_url()).load_run_restore(staged.run.id)
    assert restored is not None
    assert restored.run.current_step == 0
    assert restored.checkpoint.step_no == 0
    assert restored.outcome_count == 0
    with psycopg.connect(_url()) as connection:
        status = connection.execute(
            "SELECT status FROM public.actions WHERE id = %s",
            (staged.action.id,),
        ).fetchone()
    assert status == ("proposed",)


def test_live_gate_uses_two_fresh_processes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_p2.py"), "--live"],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0
    assert "Process A persisted and exited; fresh Process B restored" in result.stdout
