"""P1 deterministic scenario orchestration without memory, LLM, or cloud logic."""

from dataclasses import dataclass, field

from backend.app.devices.faults import DeviceOperationError, FaultId
from backend.app.devices.simulator import SimulatorLab
from backend.app.models.trace import (
    AttemptedAction,
    ErrorDetail,
    JSONValue,
    Observation,
    Outcome,
    ScenarioTrace,
)

SCENARIO_A_ID = "scenario-a-connection-recovery-v1"
SCENARIO_B_ID = "scenario-b-anomaly-baseline-v1"
DEFAULT_SCENARIO_A_SEED = 101
DEFAULT_SCENARIO_B_SEED = 202


@dataclass(slots=True)
class _TraceBuilder:
    scenario_id: str
    seed: int
    next_order: int = 1
    observations: list[Observation] = field(default_factory=list)
    actions: list[AttemptedAction] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)

    def observe(
        self, device_id: str, observation_type: str, payload: dict[str, JSONValue]
    ) -> Observation:
        record = Observation(self.next_order, device_id, observation_type, payload)
        self.next_order += 1
        self.observations.append(record)
        return record

    def attempt(
        self, device_id: str, action_type: str, parameters: dict[str, JSONValue]
    ) -> AttemptedAction:
        record = AttemptedAction(self.next_order, device_id, action_type, parameters)
        self.next_order += 1
        self.actions.append(record)
        return record

    def outcome(
        self,
        action: AttemptedAction,
        *,
        success: bool,
        result: dict[str, JSONValue],
        error: DeviceOperationError | None = None,
    ) -> Outcome:
        error_detail = None if error is None else ErrorDetail(error.code, error.message)
        record = Outcome(
            order=self.next_order,
            device_id=action.device_id,
            action_order=action.order,
            success=success,
            result=result,
            error=error_detail,
        )
        self.next_order += 1
        self.outcomes.append(record)
        return record

    def build(self, lab: SimulatorLab) -> ScenarioTrace:
        return ScenarioTrace(
            scenario_id=self.scenario_id,
            seed=self.seed,
            observations=tuple(self.observations),
            attempted_actions=tuple(self.actions),
            outcomes=tuple(self.outcomes),
            checkpoint_state=lab.checkpoint_state(),
        )


def _numeric(payload: dict[str, JSONValue], key: str) -> float:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Expected numeric simulator value for {key}")
    return float(value)


def run_scenario_a(seed: int = DEFAULT_SCENARIO_A_SEED) -> ScenarioTrace:
    """Run the generic no-memory connection recovery foundation."""

    lab = SimulatorLab(seed)
    scope = lab.scope
    builder = _TraceBuilder(SCENARIO_A_ID, seed)
    lab.inject_fault(FaultId.STALE_RESOURCE)

    builder.observe(
        scope.device_id,
        "connection_state",
        {
            "connection_state": scope.connection_state.value,
            "resource_hint_status": "stale",
            "fault_id": FaultId.STALE_RESOURCE.value,
        },
    )

    connect_action = builder.attempt(
        scope.device_id,
        "connect",
        {"resource_source": "cached_hint"},
    )
    try:
        result = scope.connect(scope.resource_hint)
        builder.outcome(connect_action, success=True, result=result)
    except DeviceOperationError as error:
        builder.outcome(connect_action, success=False, result={}, error=error)

    discover_action = builder.attempt(scope.device_id, "rediscover_resources", {})
    resources = scope.discover()
    builder.outcome(
        discover_action,
        success=True,
        result={"candidate_count": len(resources), "resource_hint_status": "refreshed"},
    )

    reconnect_action = builder.attempt(
        scope.device_id,
        "connect",
        {"resource_source": "discovered_candidate"},
    )
    builder.outcome(reconnect_action, success=True, result=scope.connect(resources[0]))

    identify_action = builder.attempt(scope.device_id, "identify", {})
    identity = scope.identify()
    builder.outcome(identify_action, success=True, result=identity)

    builder.observe(
        scope.device_id,
        "connection_recovery_verified",
        {
            "connection_state": scope.connection_state.value,
            "identity_verified": identity["device_id"] == scope.device_id,
        },
    )
    return builder.build(lab)


def run_scenario_b(seed: int = DEFAULT_SCENARIO_B_SEED) -> ScenarioTrace:
    """Run the truthful no-memory anomaly and two-step intervention baseline."""

    lab = SimulatorLab(seed)
    source = lab.signal_source
    scope = lab.scope
    temperature = lab.temperature
    builder = _TraceBuilder(SCENARIO_B_ID, seed)

    for device in (source, scope, temperature):
        device.connect()
    lab.inject_fault(FaultId.TEMPERATURE_DRIFT)
    lab.inject_fault(FaultId.NOISE_RISE)
    lab.inject_fault(FaultId.CALIBRATION_SUPERSEDED)

    initial_temperature = temperature.acquire()
    before = scope.acquire()
    builder.observe(
        scope.device_id,
        "experimental_anomaly",
        {
            "temperature_c": initial_temperature["temperature_c"],
            "noise_rms": before["noise_rms"],
            "signal_quality": before["signal_quality"],
            "drive_amplitude": before["drive_amplitude"],
            "fault_ids": [
                FaultId.TEMPERATURE_DRIFT.value,
                FaultId.NOISE_RISE.value,
                FaultId.CALIBRATION_SUPERSEDED.value,
            ],
        },
    )

    calibration_action = builder.attempt(
        scope.device_id,
        "calibration_A",
        {"calibration": "A"},
    )
    try:
        calibration_result = scope.write_safe_setting("calibration", "A")
        builder.outcome(calibration_action, success=True, result=calibration_result)
    except DeviceOperationError as error:
        builder.outcome(calibration_action, success=False, result={}, error=error)

    previous_drive = _numeric(source.read_settings(), "drive_amplitude")
    reduced_drive = round(previous_drive * 0.9, 4)
    reduction_action = builder.attempt(
        source.device_id,
        "reduce_drive_10_percent",
        {"from": previous_drive, "to": reduced_drive},
    )
    source.write_safe_setting("drive_amplitude", reduced_drive)
    after = scope.acquire()
    noise_improved = _numeric(after, "noise_rms") < _numeric(before, "noise_rms")
    quality_improved = _numeric(after, "signal_quality") > _numeric(before, "signal_quality")
    intervention_success = noise_improved and quality_improved
    builder.outcome(
        reduction_action,
        success=intervention_success,
        result={
            "before_noise_rms": before["noise_rms"],
            "after_noise_rms": after["noise_rms"],
            "before_signal_quality": before["signal_quality"],
            "after_signal_quality": after["signal_quality"],
            "noise_improved": noise_improved,
            "signal_quality_improved": quality_improved,
        },
    )
    builder.observe(
        scope.device_id,
        "post_intervention_measurement",
        {
            "temperature_c": after["temperature_c"],
            "noise_rms": after["noise_rms"],
            "signal_quality": after["signal_quality"],
            "drive_amplitude": after["drive_amplitude"],
        },
    )
    return builder.build(lab)


def run_scenario(scenario_id: str, *, seed: int | None = None) -> ScenarioTrace:
    """Resolve a stable scenario ID or CLI alias and run it deterministically."""

    if scenario_id in {"scenario-a", SCENARIO_A_ID}:
        return run_scenario_a(DEFAULT_SCENARIO_A_SEED if seed is None else seed)
    if scenario_id in {"scenario-b", SCENARIO_B_ID}:
        return run_scenario_b(DEFAULT_SCENARIO_B_SEED if seed is None else seed)
    raise ValueError(f"Unknown scenario: {scenario_id}")
