"""Stable deterministic fault identifiers and simulator operation errors."""

from enum import StrEnum

from backend.app.models.trace import JSONValue


class FaultId(StrEnum):
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    STALE_RESOURCE = "STALE_RESOURCE"
    WRONG_IDENTITY = "WRONG_IDENTITY"
    MUX_CHANNEL_SWAP = "MUX_CHANNEL_SWAP"
    CALIBRATION_SUPERSEDED = "CALIBRATION_SUPERSEDED"
    TEMPERATURE_DRIFT = "TEMPERATURE_DRIFT"
    NOISE_RISE = "NOISE_RISE"
    SIGNAL_COLLAPSE = "SIGNAL_COLLAPSE"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"


class DeviceOperationError(RuntimeError):
    """Expected simulator failure with stable machine-readable detail."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else details
