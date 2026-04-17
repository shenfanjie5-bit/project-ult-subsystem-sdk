"""Reusable runtime context for subsystem implementations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, cast, get_args

from subsystem_sdk.base.registration import SubsystemRegistrationSpec
from subsystem_sdk.heartbeat.client import HeartbeatClient
from subsystem_sdk.heartbeat.payload import HeartbeatStatus, build_ex0_payload
from subsystem_sdk.submit.client import SubmitClient
from subsystem_sdk.submit.receipt import SubmitReceipt, normalize_receipt
from subsystem_sdk.validate.engine import validate_payload as default_validate_payload
from subsystem_sdk.validate.result import ExType, ValidationResult

_REGISTRATION_SCHEMA_VERSION: Final[str] = "registration"
_FALLBACK_EX_TYPE: Final[ExType] = "Ex-0"
_VALIDATION_EX_TYPES: Final[frozenset[str]] = frozenset(get_args(ExType))


def _result_ex_type(ex_type: Any) -> ExType:
    if isinstance(ex_type, str) and ex_type in _VALIDATION_EX_TYPES:
        return cast(ExType, ex_type)
    return _FALLBACK_EX_TYPE


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
        registration_result = self._validate_registration_support(payload)
        if registration_result is not None:
            return registration_result
        return self.validator(payload)

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        registration_result = self._validate_registration_support(payload)
        if registration_result is not None:
            return normalize_receipt(
                accepted=False,
                backend_kind=self.submit_client.backend.backend_kind,
                transport_ref=None,
                validator_version=registration_result.schema_version,
                warnings=registration_result.warnings,
                errors=registration_result.field_errors,
            )
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

    def _validate_registration_support(
        self,
        payload: Mapping[str, Any],
    ) -> ValidationResult | None:
        ex_type = payload.get("ex_type")
        if ex_type is None:
            error = "producer payload must declare ex_type"
        elif not isinstance(ex_type, str):
            error = "producer payload ex_type must be a string"
        elif ex_type not in self.registration.supported_ex_types:
            supported = ", ".join(
                repr(supported_ex_type)
                for supported_ex_type in self.registration.supported_ex_types
            )
            error = (
                f"registration {self.registration.subsystem_id!r} does not "
                f"support Ex type {ex_type!r}; supported Ex type(s): {supported}"
            )
        else:
            return None

        return ValidationResult.fail(
            ex_type=_result_ex_type(ex_type),
            schema_version=_REGISTRATION_SCHEMA_VERSION,
            field_errors=(error,),
        )
