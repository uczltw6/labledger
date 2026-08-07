"""Typed domain contracts shared by local LabLedger components."""

from .trace import AttemptedAction, ErrorDetail, Observation, Outcome, ScenarioTrace

__all__ = [
    "AttemptedAction",
    "ErrorDetail",
    "Observation",
    "Outcome",
    "ScenarioTrace",
]
