"""Deterministic four-device laboratory simulator and P1 command-line entry point."""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from backend.app.devices.base import ConnectionState, DeviceAdapter
from backend.app.devices.faults import DeviceOperationError, FaultId
from backend.app.models.trace import JSONValue

if TYPE_CHECKING:
    from backend.app.models.trace import ScenarioTrace


@dataclass(slots=True)
class LabState:
    """Shared physical state used to derive measurements instead of canned outcomes."""

    seed: int
    base_temperature_c: float
    base_noise_rms: float
    drive_amplitude: float = 1.0
    active_calibration: str = "B"
    active_mux_channel: int = 1
    mux_mapping: dict[int, str] = field(default_factory=lambda: {1: "input_a", 2: "input_b"})
    active_faults: set[FaultId] = field(default_factory=set)

    @classmethod
    def from_seed(cls, seed: int) -> LabState:
        generator = random.Random(seed)
        return cls(
            seed=seed,
            base_temperature_c=round(22.0 + generator.uniform(-0.2, 0.2), 4),
            base_noise_rms=round(0.04 + generator.uniform(-0.003, 0.003), 4),
        )

    def temperature_c(self) -> float:
        drift = 15.0 if FaultId.TEMPERATURE_DRIFT in self.active_faults else 0.0
        return round(self.base_temperature_c + drift, 4)

    def scope_metrics(self) -> dict[str, JSONValue]:
        temperature = self.temperature_c()
        thermal_noise = max(0.0, temperature - 25.0) * 0.01
        injected_noise = 0.18 if FaultId.NOISE_RISE in self.active_faults else 0.0
        overload_noise = max(0.0, self.drive_amplitude - 0.9) * 1.5
        noise_rms = self.base_noise_rms + thermal_noise + injected_noise + overload_noise
        signal_factor = 0.25 if FaultId.SIGNAL_COLLAPSE in self.active_faults else 1.0
        signal_level = self.drive_amplitude * signal_factor
        signal_quality = signal_level / (signal_level + (2.0 * noise_rms))
        return {
            "temperature_c": round(temperature, 4),
            "drive_amplitude": round(self.drive_amplitude, 4),
            "noise_rms": round(noise_rms, 4),
            "signal_level": round(signal_level, 4),
            "signal_quality": round(signal_quality, 4),
        }


class SimulatedDevice(DeviceAdapter):
    """Common deterministic connection behavior for all simulated devices."""

    supported_faults: ClassVar[frozenset[FaultId]] = frozenset({FaultId.TOOL_TIMEOUT})

    def __init__(
        self,
        *,
        device_id: str,
        device_type: str,
        resource: str,
        vendor: str,
        model: str,
        lab_state: LabState,
    ) -> None:
        self._device_id = device_id
        self.device_type = device_type
        self.expected_resource = resource
        self.resource_hint = resource
        self.vendor = vendor
        self.model = model
        self.lab_state = lab_state
        self._connection_state = ConnectionState.DISCONNECTED
        self.connected_resource: str | None = None
        self.faults: set[FaultId] = set()

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def connection_state(self) -> ConnectionState:
        return self._connection_state

    def inject_fault(self, fault: FaultId) -> None:
        if fault not in self.supported_faults:
            raise DeviceOperationError(
                "UNSUPPORTED_FAULT",
                f"{fault.value} is not supported by {self.device_id}",
                details={"fault_id": fault.value, "device_id": self.device_id},
            )
        self.faults.add(fault)
        self.lab_state.active_faults.add(fault)
        if fault is FaultId.STALE_RESOURCE:
            self.resource_hint = f"{self.expected_resource}::STALE"

    def clear_fault(self, fault: FaultId) -> None:
        self.faults.discard(fault)
        self.lab_state.active_faults.discard(fault)
        if fault is FaultId.STALE_RESOURCE:
            self.resource_hint = self.expected_resource

    def _guard_tool(self, operation: str) -> None:
        if FaultId.TOOL_TIMEOUT in self.faults:
            raise DeviceOperationError(
                FaultId.TOOL_TIMEOUT.value,
                f"{operation} timed out deterministically",
                details={"operation": operation, "device_id": self.device_id},
            )

    def _require_connected(self, operation: str) -> None:
        if self.connection_state is not ConnectionState.CONNECTED:
            raise DeviceOperationError(
                "NOT_CONNECTED",
                f"{operation} requires a connected device",
                details={"device_id": self.device_id},
            )

    def discover(self) -> list[str]:
        self._guard_tool("discover")
        self.resource_hint = self.expected_resource
        if self.connection_state is ConnectionState.FAULT:
            self._connection_state = ConnectionState.DISCONNECTED
        return [self.expected_resource]

    def connect(self, resource: str | None = None) -> dict[str, JSONValue]:
        self._guard_tool("connect")
        selected_resource = self.resource_hint if resource is None else resource
        if FaultId.CONNECTION_TIMEOUT in self.faults:
            self._connection_state = ConnectionState.FAULT
            raise DeviceOperationError(
                FaultId.CONNECTION_TIMEOUT.value,
                "Connection attempt timed out deterministically",
                details={"device_id": self.device_id},
            )
        if selected_resource != self.expected_resource:
            self._connection_state = ConnectionState.FAULT
            code = (
                FaultId.STALE_RESOURCE.value
                if FaultId.STALE_RESOURCE in self.faults
                else "RESOURCE_NOT_FOUND"
            )
            raise DeviceOperationError(
                code,
                "Requested resource does not match the discovered resource",
                details={"device_id": self.device_id},
            )
        self.connected_resource = selected_resource
        self.resource_hint = selected_resource
        self._connection_state = ConnectionState.CONNECTED
        return {
            "device_id": self.device_id,
            "connection_state": self.connection_state.value,
        }

    def identify(self) -> dict[str, JSONValue]:
        self._guard_tool("identify")
        self._require_connected("identify")
        if FaultId.WRONG_IDENTITY in self.faults:
            raise DeviceOperationError(
                FaultId.WRONG_IDENTITY.value,
                "Device identity did not match the expected logical device",
                details={
                    "device_id": self.device_id,
                    "observed_device_id": "unexpected_device",
                },
            )
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "vendor": self.vendor,
            "model": self.model,
        }

    def read_settings(self) -> dict[str, JSONValue]:
        self._guard_tool("read_settings")
        self._require_connected("read_settings")
        return {"connection_state": self.connection_state.value}

    def self_test(self) -> dict[str, JSONValue]:
        self._guard_tool("self_test")
        self._require_connected("self_test")
        return {"device_id": self.device_id, "passed": True}

    def disconnect(self) -> dict[str, JSONValue]:
        self.connected_resource = None
        self._connection_state = ConnectionState.DISCONNECTED
        return {
            "device_id": self.device_id,
            "connection_state": self.connection_state.value,
        }


class SignalSourceDevice(SimulatedDevice):
    supported_faults = frozenset({FaultId.TOOL_TIMEOUT})

    def read_settings(self) -> dict[str, JSONValue]:
        settings = super().read_settings()
        settings["drive_amplitude"] = round(self.lab_state.drive_amplitude, 4)
        return settings

    def write_safe_setting(self, setting: str, value: JSONValue) -> dict[str, JSONValue]:
        self._guard_tool("write_safe_setting")
        self._require_connected("write_safe_setting")
        if setting != "drive_amplitude":
            raise DeviceOperationError(
                "UNSUPPORTED_SETTING", f"Unsupported signal-source setting: {setting}"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DeviceOperationError("INVALID_SETTING_VALUE", "drive_amplitude must be numeric")
        amplitude = float(value)
        if not 0.1 <= amplitude <= 1.0:
            raise DeviceOperationError(
                "OUT_OF_RANGE", "drive_amplitude must remain within [0.1, 1.0]"
            )
        self.lab_state.drive_amplitude = round(amplitude, 4)
        return {"drive_amplitude": self.lab_state.drive_amplitude}

    def acquire(self) -> dict[str, JSONValue]:
        self._guard_tool("acquire")
        self._require_connected("acquire")
        return {
            "drive_amplitude": round(self.lab_state.drive_amplitude, 4),
            "output_enabled": True,
        }


class ScopeDevice(SimulatedDevice):
    supported_faults = frozenset(
        {
            FaultId.CALIBRATION_SUPERSEDED,
            FaultId.CONNECTION_TIMEOUT,
            FaultId.NOISE_RISE,
            FaultId.SIGNAL_COLLAPSE,
            FaultId.STALE_RESOURCE,
            FaultId.TOOL_TIMEOUT,
            FaultId.WRONG_IDENTITY,
        }
    )

    def read_settings(self) -> dict[str, JSONValue]:
        settings = super().read_settings()
        settings.update(
            {
                "calibration": self.lab_state.active_calibration,
                "sample_rate_hz": 1_000_000,
            }
        )
        return settings

    def write_safe_setting(self, setting: str, value: JSONValue) -> dict[str, JSONValue]:
        self._guard_tool("write_safe_setting")
        self._require_connected("write_safe_setting")
        if setting != "calibration":
            raise DeviceOperationError(
                "UNSUPPORTED_SETTING", f"Unsupported scope setting: {setting}"
            )
        if not isinstance(value, str) or value not in {"A", "B"}:
            raise DeviceOperationError("INVALID_SETTING_VALUE", "calibration must be either A or B")
        if value == "A" and FaultId.CALIBRATION_SUPERSEDED in self.faults:
            raise DeviceOperationError(
                FaultId.CALIBRATION_SUPERSEDED.value,
                "Calibration A is superseded and cannot be applied",
                details={"requested_calibration": value},
            )
        self.lab_state.active_calibration = value
        return {"calibration": self.lab_state.active_calibration}

    def acquire(self) -> dict[str, JSONValue]:
        self._guard_tool("acquire")
        self._require_connected("acquire")
        return self.lab_state.scope_metrics()


class MuxDevice(SimulatedDevice):
    supported_faults = frozenset({FaultId.MUX_CHANNEL_SWAP, FaultId.TOOL_TIMEOUT})

    def read_settings(self) -> dict[str, JSONValue]:
        settings = super().read_settings()
        mapping = self._effective_mapping()
        settings.update(
            {
                "active_channel": self.lab_state.active_mux_channel,
                "channel_mapping": {str(key): value for key, value in mapping.items()},
            }
        )
        return settings

    def _effective_mapping(self) -> dict[int, str]:
        if FaultId.MUX_CHANNEL_SWAP in self.faults:
            return {1: self.lab_state.mux_mapping[2], 2: self.lab_state.mux_mapping[1]}
        return dict(self.lab_state.mux_mapping)

    def write_safe_setting(self, setting: str, value: JSONValue) -> dict[str, JSONValue]:
        self._guard_tool("write_safe_setting")
        self._require_connected("write_safe_setting")
        if setting != "active_channel":
            raise DeviceOperationError("UNSUPPORTED_SETTING", f"Unsupported MUX setting: {setting}")
        if isinstance(value, bool) or not isinstance(value, int) or value not in {1, 2}:
            raise DeviceOperationError(
                "INVALID_SETTING_VALUE", "active_channel must be integer 1 or 2"
            )
        self.lab_state.active_mux_channel = value
        return {"active_channel": value}

    def acquire(self) -> dict[str, JSONValue]:
        self._guard_tool("acquire")
        self._require_connected("acquire")
        mapping = self._effective_mapping()
        channel = self.lab_state.active_mux_channel
        return {"active_channel": channel, "input_source": mapping[channel]}


class TemperatureDevice(SimulatedDevice):
    supported_faults = frozenset({FaultId.TEMPERATURE_DRIFT, FaultId.TOOL_TIMEOUT})

    def read_settings(self) -> dict[str, JSONValue]:
        settings = super().read_settings()
        settings["unit"] = "celsius"
        return settings

    def write_safe_setting(self, setting: str, value: JSONValue) -> dict[str, JSONValue]:
        del value
        self._guard_tool("write_safe_setting")
        self._require_connected("write_safe_setting")
        raise DeviceOperationError(
            "UNSUPPORTED_SETTING", f"Temperature sensor is read-only: {setting}"
        )

    def acquire(self) -> dict[str, JSONValue]:
        self._guard_tool("acquire")
        self._require_connected("acquire")
        return {"temperature_c": self.lab_state.temperature_c()}


class SimulatorLab:
    """Deterministic mixed-instrument test bench with explicit fault routing."""

    _FAULT_DEVICE: ClassVar[dict[FaultId, str]] = {
        FaultId.CONNECTION_TIMEOUT: "scope_01",
        FaultId.STALE_RESOURCE: "scope_01",
        FaultId.WRONG_IDENTITY: "scope_01",
        FaultId.MUX_CHANNEL_SWAP: "mux_01",
        FaultId.CALIBRATION_SUPERSEDED: "scope_01",
        FaultId.TEMPERATURE_DRIFT: "temperature_01",
        FaultId.NOISE_RISE: "scope_01",
        FaultId.SIGNAL_COLLAPSE: "scope_01",
        FaultId.TOOL_TIMEOUT: "scope_01",
    }

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.state = LabState.from_seed(seed)
        self.signal_source = SignalSourceDevice(
            device_id="signal_source_01",
            device_type="signal_source",
            resource="SIM::SOURCE::01",
            vendor="Synthetic Instruments",
            model="SS-100",
            lab_state=self.state,
        )
        self.scope = ScopeDevice(
            device_id="scope_01",
            device_type="oscilloscope",
            resource="SIM::SCOPE::01",
            vendor="Synthetic Instruments",
            model="SCOPE-200",
            lab_state=self.state,
        )
        self.mux = MuxDevice(
            device_id="mux_01",
            device_type="multiplexer",
            resource="SIM::MUX::01",
            vendor="Synthetic Instruments",
            model="MUX-8",
            lab_state=self.state,
        )
        self.temperature = TemperatureDevice(
            device_id="temperature_01",
            device_type="temperature_sensor",
            resource="SIM::TEMP::01",
            vendor="Synthetic Instruments",
            model="TEMP-1",
            lab_state=self.state,
        )
        self.devices: dict[str, SimulatedDevice] = {
            device.device_id: device
            for device in (self.signal_source, self.scope, self.mux, self.temperature)
        }

    def get_device(self, device_id: str) -> SimulatedDevice:
        try:
            return self.devices[device_id]
        except KeyError as error:
            raise DeviceOperationError(
                "UNKNOWN_DEVICE", f"Unknown simulator device: {device_id}"
            ) from error

    def inject_fault(self, fault: FaultId, *, device_id: str | None = None) -> str:
        target_id = self._FAULT_DEVICE[fault] if device_id is None else device_id
        self.get_device(target_id).inject_fault(fault)
        return target_id

    def clear_fault(self, fault: FaultId, *, device_id: str | None = None) -> str:
        target_id = self._FAULT_DEVICE[fault] if device_id is None else device_id
        self.get_device(target_id).clear_fault(fault)
        return target_id


def _human_trace(trace: ScenarioTrace) -> str:
    lines = [f"Scenario: {trace.scenario_id} (seed={trace.seed})"]
    for record in trace.ordered_records():
        label = record.get("observation_type") or record.get("action_type")
        label = record.get("success") if label is None else label
        order = record["order"]
        if isinstance(order, bool) or not isinstance(order, int):
            raise TypeError("Trace record order must be an integer")
        lines.append(f"{order:02d} {record['record_type']}: {label}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one or both deterministic P1 scenarios."""

    from backend.app.devices.scenarios import (
        SCENARIO_A_ID,
        SCENARIO_B_ID,
        run_scenario,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("scenario-a", "scenario-b", "all", SCENARIO_A_ID, SCENARIO_B_ID),
        default="all",
        help="stable scenario ID, short alias, or all",
    )
    parser.add_argument("--seed", type=int, help="override the scenario's deterministic seed")
    parser.add_argument("--json", action="store_true", help="emit canonical machine-readable JSON")
    arguments = parser.parse_args(argv)

    scenario_ids = (
        (SCENARIO_A_ID, SCENARIO_B_ID) if arguments.scenario == "all" else (arguments.scenario,)
    )
    traces = [run_scenario(scenario_id, seed=arguments.seed) for scenario_id in scenario_ids]
    if arguments.json:
        payload: dict[str, JSONValue] = {"traces": [trace.to_dict() for trace in traces]}
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    else:
        print("\n\n".join(_human_trace(trace) for trace in traces))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
