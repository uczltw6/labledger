"""Device interface shared by deterministic simulation and future adapters."""

from abc import ABC, abstractmethod
from enum import StrEnum

from backend.app.models.trace import JSONValue


class ConnectionState(StrEnum):
    """Observable connection lifecycle for a device adapter."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    FAULT = "fault"


class DeviceAdapter(ABC):
    """Small device contract that can later be implemented by PyVISA/SCPI."""

    @property
    @abstractmethod
    def device_id(self) -> str:
        """Return the stable logical device identifier."""

    @property
    @abstractmethod
    def connection_state(self) -> ConnectionState:
        """Return the current connection state."""

    @abstractmethod
    def discover(self) -> list[str]:
        """Return currently discoverable resource identifiers."""

    @abstractmethod
    def connect(self, resource: str | None = None) -> dict[str, JSONValue]:
        """Connect to the requested resource or the current resource hint."""

    @abstractmethod
    def identify(self) -> dict[str, JSONValue]:
        """Return verified device identity information."""

    @abstractmethod
    def read_settings(self) -> dict[str, JSONValue]:
        """Return current safe, observable settings."""

    @abstractmethod
    def write_safe_setting(self, setting: str, value: JSONValue) -> dict[str, JSONValue]:
        """Apply a simulator-approved setting within its safe envelope."""

    @abstractmethod
    def acquire(self) -> dict[str, JSONValue]:
        """Acquire one deterministic device sample."""

    @abstractmethod
    def self_test(self) -> dict[str, JSONValue]:
        """Run a non-destructive deterministic self-test."""

    @abstractmethod
    def disconnect(self) -> dict[str, JSONValue]:
        """Disconnect without changing device settings."""
