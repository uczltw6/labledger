"""Unit tests for the four deterministic simulator devices."""

import pytest

from backend.app.devices import ConnectionState, DeviceAdapter, DeviceOperationError
from backend.app.devices.simulator import SimulatorLab


@pytest.mark.parametrize(
    "device_attribute",
    ("signal_source", "scope", "mux", "temperature"),
)
def test_all_four_devices_implement_adapter_lifecycle(device_attribute: str) -> None:
    lab = SimulatorLab(seed=11)
    device = getattr(lab, device_attribute)

    assert isinstance(device, DeviceAdapter)
    assert device.connection_state is ConnectionState.DISCONNECTED
    assert device.discover() == [device.expected_resource]
    assert device.connect()["connection_state"] == ConnectionState.CONNECTED.value
    assert device.identify()["device_id"] == device.device_id
    assert device.read_settings()["connection_state"] == ConnectionState.CONNECTED.value
    assert device.acquire()
    assert device.self_test()["passed"] is True
    assert device.disconnect()["connection_state"] == ConnectionState.DISCONNECTED.value
    assert device.connection_state is ConnectionState.DISCONNECTED


def test_supported_safe_settings_change_real_device_state() -> None:
    lab = SimulatorLab(seed=12)
    for device in (lab.signal_source, lab.scope, lab.mux):
        device.connect()

    assert lab.signal_source.write_safe_setting("drive_amplitude", 0.8) == {"drive_amplitude": 0.8}
    assert lab.signal_source.acquire()["drive_amplitude"] == 0.8
    assert lab.scope.write_safe_setting("calibration", "A") == {"calibration": "A"}
    assert lab.scope.read_settings()["calibration"] == "A"
    assert lab.mux.write_safe_setting("active_channel", 2) == {"active_channel": 2}
    assert lab.mux.acquire()["active_channel"] == 2


@pytest.mark.parametrize(
    ("device_attribute", "setting", "value", "expected_code"),
    (
        ("signal_source", "drive_amplitude", 1.5, "OUT_OF_RANGE"),
        ("signal_source", "frequency", 1000, "UNSUPPORTED_SETTING"),
        ("scope", "calibration", "Z", "INVALID_SETTING_VALUE"),
        ("mux", "active_channel", 3, "INVALID_SETTING_VALUE"),
        ("temperature", "offset", 1.0, "UNSUPPORTED_SETTING"),
    ),
)
def test_invalid_or_unsupported_safe_settings_are_rejected(
    device_attribute: str,
    setting: str,
    value: str | float | int,
    expected_code: str,
) -> None:
    lab = SimulatorLab(seed=13)
    device = getattr(lab, device_attribute)
    device.connect()

    with pytest.raises(DeviceOperationError, match=r".+") as captured:
        device.write_safe_setting(setting, value)

    assert captured.value.code == expected_code


def test_operations_require_connection_and_disconnect_is_idempotent() -> None:
    lab = SimulatorLab(seed=14)

    with pytest.raises(DeviceOperationError) as captured:
        lab.scope.acquire()

    assert captured.value.code == "NOT_CONNECTED"
    lab.scope.connect()
    lab.scope.disconnect()
    lab.scope.disconnect()
    assert lab.scope.connection_state is ConnectionState.DISCONNECTED
