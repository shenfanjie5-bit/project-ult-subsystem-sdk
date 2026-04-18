"""Reusable runtime context for subsystem implementations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, cast, get_args

from subsystem_sdk.base.registration import SubsystemRegistrationSpec
from subsystem_sdk.heartbeat.client import HeartbeatClient
from subsystem_sdk.heartbeat.payload import HeartbeatStatus, build_ex0_payload
from subsystem_sdk.submit.client import SubmitClient
from subsystem_sdk.submit.receipt import BackendKind, SubmitReceipt, normalize_receipt
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
        heartbeat_result = self._validate_heartbeat_support()
        if heartbeat_result is not None:
            return normalize_receipt(
                accepted=False,
                backend_kind=self._heartbeat_backend_kind(),
                transport_ref=None,
                validator_version=heartbeat_result.schema_version,
                warnings=heartbeat_result.warnings,
                errors=heartbeat_result.field_errors,
            )

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
        errors: list[str] = []
        ex_type = payload.get("ex_type")
        if ex_type is None:
            errors.append("producer payload must declare ex_type")
        elif not isinstance(ex_type, str):
            errors.append("producer payload ex_type must be a string")
        elif ex_type not in self.registration.supported_ex_types:
            errors.append(
                f"registration {self.registration.subsystem_id!r} does not "
                f"support Ex type {ex_type!r}; supported Ex type(s): "
                f"{self._supported_ex_types_text()}"
            )

        subsystem_id = payload.get("subsystem_id")
        if subsystem_id is not None:
            if not isinstance(subsystem_id, str):
                errors.append("producer payload subsystem_id must be a string")
            elif subsystem_id != self.registration.subsystem_id:
                errors.append(
                    "producer payload subsystem_id "
                    f"{subsystem_id!r} conflicts with registration "
                    f"{self.registration.subsystem_id!r}"
                )

        version = payload.get("version")
        if version is not None:
            if not isinstance(version, str):
                errors.append("producer payload version must be a string when present")
            elif version != self.registration.version:
                errors.append(
                    "producer payload version "
                    f"{version!r} conflicts with registration "
                    f"{self.registration.version!r}"
                )

        if not errors:
            return None

        return ValidationResult.fail(
            ex_type=_result_ex_type(ex_type),
            schema_version=_REGISTRATION_SCHEMA_VERSION,
            field_errors=tuple(errors),
        )

    def _validate_heartbeat_support(self) -> ValidationResult | None:
        if "Ex-0" in self.registration.supported_ex_types:
            return None

        return ValidationResult.fail(
            ex_type="Ex-0",
            schema_version=_REGISTRATION_SCHEMA_VERSION,
            field_errors=(
                f"registration {self.registration.subsystem_id!r} does not "
                "support Ex-0 heartbeat; supported Ex type(s): "
                f"{self._supported_ex_types_text()}",
            ),
        )

    def _supported_ex_types_text(self) -> str:
        return ", ".join(
            repr(supported_ex_type)
            for supported_ex_type in self.registration.supported_ex_types
        )

    def _heartbeat_backend_kind(self) -> BackendKind:
        heartbeat_backend = getattr(
            self.heartbeat_client,
            "backend",
            self.submit_client.backend,
        )
        return heartbeat_backend.backend_kind
