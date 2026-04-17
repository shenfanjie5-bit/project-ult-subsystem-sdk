"""Base subsystem interface and thin wrapper implementation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from subsystem_sdk.base.context import BaseSubsystemContext
from subsystem_sdk.heartbeat.payload import HeartbeatStatus
from subsystem_sdk.submit.receipt import SubmitReceipt
from subsystem_sdk.validate.result import ValidationResult


class SubsystemBaseInterface(Protocol):
    """Protocol for subsystem runtime shells."""

    context: BaseSubsystemContext

    def validate(self, payload: Mapping[str, Any]) -> ValidationResult:
        """Validate a producer payload."""

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        """Submit a producer payload."""

    def heartbeat(self, status: HeartbeatStatus | Mapping[str, Any]) -> SubmitReceipt:
        """Send a heartbeat for the subsystem."""


@dataclass(frozen=True)
class BaseSubsystem:
    """Domain-neutral subsystem runtime wrapper."""

    context: BaseSubsystemContext

    def validate(self, payload: Mapping[str, Any]) -> ValidationResult:
        return self.context.validate_payload(payload)

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        return self.context.submit(payload)

    def heartbeat(self, status: HeartbeatStatus | Mapping[str, Any]) -> SubmitReceipt:
        return self.context.send_heartbeat(status)
