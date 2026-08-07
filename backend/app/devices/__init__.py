"""Deterministic device abstractions and simulator fault contracts."""

from .base import ConnectionState, DeviceAdapter
from .faults import DeviceOperationError, FaultId

__all__ = ["ConnectionState", "DeviceAdapter", "DeviceOperationError", "FaultId"]
