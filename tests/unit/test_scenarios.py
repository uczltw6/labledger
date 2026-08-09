"""Acceptance-focused tests for deterministic Scenario A/B traces and CLI JSON."""

import json
import subprocess
import sys
from pathlib import Path

from backend.app.devices.scenarios import (
    SCENARIO_A_ID,
    SCENARIO_B_ID,
    run_scenario_a,
    run_scenario_b,
)

ROOT = Path(__file__).resolve().parents[2]


def test_scenario_a_expected_connection_recovery_trace() -> None:
    trace = run_scenario_a()

    assert trace.scenario_id == SCENARIO_A_ID
    assert [action.action_type for action in trace.attempted_actions] == [
        "connect",
        "rediscover_resources",
        "connect",
        "identify",
    ]
    assert [outcome.success for outcome in trace.outcomes] == [False, True, True, True]
    assert trace.outcomes[0].error is not None
    assert trace.outcomes[0].error.code == "STALE_RESOURCE"
    assert trace.observations[-1].payload["connection_state"] == "connected"
    assert trace.observations[-1].payload["identity_verified"] is True
    scope_state = trace.checkpoint_state["devices"]["scope_01"]
    assert scope_state["connection_state"] == "connected"
    assert scope_state["active_faults"] == []


def test_scenario_b_expected_no_memory_baseline_trace() -> None:
    trace = run_scenario_b()

    assert trace.scenario_id == SCENARIO_B_ID
    assert [action.action_type for action in trace.attempted_actions] == [
        "calibration_A",
        "reduce_drive_10_percent",
    ]
    assert [outcome.success for outcome in trace.outcomes] == [False, True]
    assert trace.outcomes[0].error is not None
    assert trace.outcomes[0].error.code == "CALIBRATION_SUPERSEDED"
    physical_state = trace.checkpoint_state["physical_state"]
    assert physical_state["drive_amplitude"] == 0.9
    assert physical_state["active_calibration"] == "B"


def test_scenario_b_success_is_backed_by_measurable_state_improvement() -> None:
    trace = run_scenario_b()
    result = trace.outcomes[1].result

    assert float(result["after_noise_rms"]) < float(result["before_noise_rms"])
    assert float(result["after_signal_quality"]) > float(result["before_signal_quality"])
    assert result["noise_improved"] is True
    assert result["signal_quality_improved"] is True


def test_same_scenario_and_seed_produce_identical_machine_readable_trace() -> None:
    first = run_scenario_b(seed=707).to_json()
    second = run_scenario_b(seed=707).to_json()

    assert first == second


def test_different_seed_changes_measured_trace_without_changing_scenario_id() -> None:
    first = run_scenario_b(seed=707)
    second = run_scenario_b(seed=708)

    assert first.scenario_id == second.scenario_id == SCENARIO_B_ID
    assert first.to_json() != second.to_json()


def test_cli_all_json_exposes_observations_actions_outcomes_and_ids() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.app.devices.simulator",
            "--scenario",
            "all",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert [trace["scenario_id"] for trace in payload["traces"]] == [
        SCENARIO_A_ID,
        SCENARIO_B_ID,
    ]
    for trace in payload["traces"]:
        assert trace["observations"]
        assert trace["attempted_actions"]
        assert trace["outcomes"]
        assert trace["checkpoint_state"]
        assert [record["order"] for record in trace["records"]] == sorted(
            record["order"] for record in trace["records"]
        )
