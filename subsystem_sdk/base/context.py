"""Reusable runtime context for subsystem implementations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from subsystem_sdk.base.registration import SubsystemRegistrationSpec
from subsystem_sdk.heartbeat.client import HeartbeatClient
from subsystem_sdk.heartbeat.payload import HeartbeatStatus, build_ex0_payload
from subsystem_sdk.submit.client import SubmitClient
from subsystem_sdk.submit.receipt import SubmitReceipt
from subsystem_sdk.validate.engine import validate_payload as default_validate_payload
from subsystem_sdk.validate.result import ValidationResult


@dataclass(frozen=True)
class BaseSubsystemContext:
    """Runtime shell that wires validation, submit, and heartbeat clients."""

    registration: SubsystemRegistrationSpec
    submit_client: SubmitClient
    heartbeat_client: HeartbeatClient
    validator: Callable[[Mapping[str, Any]], ValidationResult] = (
        default_validate_payload
    )
    fixture_bundle_ref: str | None = None

    def validate_payload(self, payload: Mapping[str, Any]) -> ValidationResult:
        return self.validator(payload)

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        return self.submit_client.submit(payload)

    def send_heartbeat(
        self,
        status: HeartbeatStatus | Mapping[str, Any],
    ) -> SubmitReceipt:
        ex0_payload = build_ex0_payload(
            self.registration.subsystem_id,
            self.registration.version,
            status,
        )
        return self.heartbeat_client.send_heartbeat(ex0_payload)
