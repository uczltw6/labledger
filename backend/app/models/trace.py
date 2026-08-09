"""Stable, database-agnostic records emitted by deterministic simulator scenarios."""

import json
from dataclasses import dataclass

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(frozen=True, slots=True)
class Observation:
    """A measured or directly inspected simulator state."""

    order: int
    device_id: str
    observation_type: str
    payload: dict[str, JSONValue]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "record_type": "observation",
            "order": self.order,
            "device_id": self.device_id,
            "observation_type": self.observation_type,
            "payload": self.payload,
        }


@dataclass(frozen=True, slots=True)
class AttemptedAction:
    """An action the deterministic scenario attempted to execute."""

    order: int
    device_id: str
    action_type: str
    parameters: dict[str, JSONValue]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "record_type": "attempted_action",
            "order": self.order,
            "device_id": self.device_id,
            "action_type": self.action_type,
            "parameters": self.parameters,
        }


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    """Stable simulator error information suitable for later persistence."""

    code: str
    message: str

    def to_dict(self) -> dict[str, JSONValue]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class Outcome:
    """The measured result of an attempted action."""

    order: int
    device_id: str
    action_order: int
    success: bool
    result: dict[str, JSONValue]
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "record_type": "outcome",
            "order": self.order,
            "device_id": self.device_id,
            "action_order": self.action_order,
            "success": self.success,
            "result": self.result,
            "error": None if self.error is None else self.error.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ScenarioTrace:
    """Machine-readable trace for one stable deterministic scenario."""

    scenario_id: str
    seed: int
    observations: tuple[Observation, ...]
    attempted_actions: tuple[AttemptedAction, ...]
    outcomes: tuple[Outcome, ...]
    checkpoint_state: dict[str, JSONValue]

    def ordered_records(self) -> list[dict[str, JSONValue]]:
        records = [
            *(observation.to_dict() for observation in self.observations),
            *(action.to_dict() for action in self.attempted_actions),
            *(outcome.to_dict() for outcome in self.outcomes),
        ]
        return sorted(records, key=_record_order)

    def to_dict(self) -> dict[str, JSONValue]:
        observations: list[JSONValue] = [record.to_dict() for record in self.observations]
        actions: list[JSONValue] = [record.to_dict() for record in self.attempted_actions]
        outcomes: list[JSONValue] = [record.to_dict() for record in self.outcomes]
        ordered_records: list[JSONValue] = [record for record in self.ordered_records()]
        return {
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "observations": observations,
            "attempted_actions": actions,
            "outcomes": outcomes,
            "records": ordered_records,
            "checkpoint_state": self.checkpoint_state,
        }

    def to_json(self) -> str:
        """Return canonical JSON so identical traces are byte-for-byte equal."""

        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _record_order(record: dict[str, JSONValue]) -> int:
    value = record["order"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Trace record order must be an integer")
    return value
