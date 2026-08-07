"""Behavioral tests for every required deterministic fault transition."""

import pytest

from backend.app.devices import ConnectionState, DeviceOperationError, FaultId
from backend.app.devices.simulator import SimulatorLab


def _number(value: object) -> float:
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value)


def test_every_required_fault_identifier_is_implemented() -> None:
    assert {fault.value for fault in FaultId} == {
        "CONNECTION_TIMEOUT",
        "STALE_RESOURCE",
        "WRONG_IDENTITY",
        "MUX_CHANNEL_SWAP",
        "CALIBRATION_SUPERSEDED",
        "TEMPERATURE_DRIFT",
        "NOISE_RISE",
        "SIGNAL_COLLAPSE",
        "TOOL_TIMEOUT",
    }


def test_connection_timeout_changes_connection_state_until_cleared() -> None:
    lab = SimulatorLab(seed=21)
    lab.inject_fault(FaultId.CONNECTION_TIMEOUT)

    with pytest.raises(DeviceOperationError) as captured:
        lab.scope.connect()

    assert captured.value.code == FaultId.CONNECTION_TIMEOUT.value
    assert lab.scope.connection_state is ConnectionState.FAULT
    lab.clear_fault(FaultId.CONNECTION_TIMEOUT)
    assert lab.scope.connect()["connection_state"] == ConnectionState.CONNECTED.value


def test_stale_resource_requires_rediscovery_before_connecting() -> None:
    lab = SimulatorLab(seed=22)
    lab.inject_fault(FaultId.STALE_RESOURCE)
    stale_hint = lab.scope.resource_hint

    with pytest.raises(DeviceOperationError) as captured:
        lab.scope.connect(stale_hint)

    assert captured.value.code == FaultId.STALE_RESOURCE.value
    assert lab.scope.connection_state is ConnectionState.FAULT
    resources = lab.scope.discover()
    assert lab.scope.connection_state is ConnectionState.DISCONNECTED
    assert lab.scope.connect(resources[0])["connection_state"] == ConnectionState.CONNECTED.value


def test_wrong_identity_is_observable_after_connection() -> None:
    lab = SimulatorLab(seed=23)
    lab.scope.connect()
    lab.inject_fault(FaultId.WRONG_IDENTITY)

    with pytest.raises(DeviceOperationError) as captured:
        lab.scope.identify()

    assert captured.value.code == FaultId.WRONG_IDENTITY.value


def test_mux_channel_swap_changes_acquired_input() -> None:
    baseline = SimulatorLab(seed=24)
    baseline.mux.connect()
    expected_source = baseline.mux.acquire()["input_source"]

    faulty = SimulatorLab(seed=24)
    faulty.mux.connect()
    faulty.inject_fault(FaultId.MUX_CHANNEL_SWAP)
    swapped_source = faulty.mux.acquire()["input_source"]

    assert expected_source == "input_a"
    assert swapped_source == "input_b"


def test_superseded_calibration_blocks_the_setting() -> None:
    lab = SimulatorLab(seed=25)
    lab.scope.connect()
    lab.inject_fault(FaultId.CALIBRATION_SUPERSEDED)

    with pytest.raises(DeviceOperationError) as captured:
        lab.scope.write_safe_setting("calibration", "A")

    assert captured.value.code == FaultId.CALIBRATION_SUPERSEDED.value
    assert lab.scope.read_settings()["calibration"] == "B"


def test_temperature_drift_changes_measured_temperature() -> None:
    baseline = SimulatorLab(seed=26)
    baseline.temperature.connect()
    baseline_temperature = _number(baseline.temperature.acquire()["temperature_c"])

    faulty = SimulatorLab(seed=26)
    faulty.temperature.connect()
    faulty.inject_fault(FaultId.TEMPERATURE_DRIFT)
    drift_temperature = _number(faulty.temperature.acquire()["temperature_c"])

    assert drift_temperature - baseline_temperature == pytest.approx(15.0)


def test_noise_rise_changes_scope_measurement() -> None:
    baseline = SimulatorLab(seed=27)
    baseline.scope.connect()
    baseline_noise = _number(baseline.scope.acquire()["noise_rms"])

    faulty = SimulatorLab(seed=27)
    faulty.scope.connect()
    faulty.inject_fault(FaultId.NOISE_RISE)
    raised_noise = _number(faulty.scope.acquire()["noise_rms"])

    assert raised_noise > baseline_noise


def test_signal_collapse_changes_signal_and_quality() -> None:
    baseline = SimulatorLab(seed=28)
    baseline.scope.connect()
    baseline_sample = baseline.scope.acquire()

    faulty = SimulatorLab(seed=28)
    faulty.scope.connect()
    faulty.inject_fault(FaultId.SIGNAL_COLLAPSE)
    collapsed_sample = faulty.scope.acquire()

    assert _number(collapsed_sample["signal_level"]) < _number(baseline_sample["signal_level"])
    assert _number(collapsed_sample["signal_quality"]) < _number(baseline_sample["signal_quality"])


def test_tool_timeout_blocks_an_actual_operation() -> None:
    lab = SimulatorLab(seed=29)
    lab.scope.connect()
    lab.inject_fault(FaultId.TOOL_TIMEOUT)

    with pytest.raises(DeviceOperationError) as captured:
        lab.scope.self_test()

    assert captured.value.code == FaultId.TOOL_TIMEOUT.value
