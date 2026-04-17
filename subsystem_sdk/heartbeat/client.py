"""Heartbeat client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from subsystem_sdk.heartbeat.protocol import HeartbeatBackendInterface
from subsystem_sdk.heartbeat.payload import HeartbeatStatus
from subsystem_sdk.submit.receipt import (
    SubmitReceipt,
    normalize_backend_receipt,
    normalize_receipt,
)
from subsystem_sdk.validate.engine import validate_payload
from subsystem_sdk.validate.result import ValidationResult
from subsystem_sdk.validate.semantics import EX0_SEMANTIC

_HEARTBEAT_EX_TYPE = "Ex-0"
_EX_TYPE_FIELD = "ex_type"
_SEMANTIC_FIELD = "semantic"


def _heartbeat_boundary_errors(
    status_payload: Mapping[str, Any], validation: ValidationResult
) -> tuple[str, ...]:
    errors: list[str] = []

    if validation.ex_type != _HEARTBEAT_EX_TYPE:
        errors.append(
            "heartbeat validator result must be "
            f"{_HEARTBEAT_EX_TYPE!r}; got {validation.ex_type!r}"
        )

    payload_ex_type = status_payload.get(_EX_TYPE_FIELD)
    if payload_ex_type != _HEARTBEAT_EX_TYPE:
        errors.append(
            "heartbeat payload ex_type must be "
            f"{_HEARTBEAT_EX_TYPE!r}; got {payload_ex_type!r}"
        )

    payload_semantic = status_payload.get(_SEMANTIC_FIELD)
    if payload_semantic != EX0_SEMANTIC:
        errors.append(
            "heartbeat payload semantic must be "
            f"{EX0_SEMANTIC!r}; got {payload_semantic!r}"
        )

    return tuple(errors)


class HeartbeatClient:
    """Validate Ex-0 heartbeat payloads before sending them to a backend."""

    def __init__(
        self,
        backend: HeartbeatBackendInterface,
        validator: Callable[[Mapping[str, Any]], ValidationResult] = validate_payload,
    ) -> None:
        self._backend = backend
        self._validator = validator

    @property
    def backend(self) -> HeartbeatBackendInterface:
        return self._backend

    def send_heartbeat(self, status_payload: Mapping[str, Any]) -> SubmitReceipt:
        validation = self._validator(status_payload)
        if validation.is_valid is False:
            return normalize_receipt(
                accepted=False,
                backend_kind=self._backend.backend_kind,
                transport_ref=None,
                validator_version=validation.schema_version,
                warnings=validation.warnings,
                errors=validation.field_errors,
            )

        boundary_errors = _heartbeat_boundary_errors(status_payload, validation)
        if boundary_errors:
            return normalize_receipt(
                accepted=False,
                backend_kind=self._backend.backend_kind,
                transport_ref=None,
                validator_version=validation.schema_version,
                warnings=validation.warnings,
                errors=boundary_errors,
            )

        backend_receipt = normalize_backend_receipt(
            self._backend.send(status_payload),
            backend_kind=self._backend.backend_kind,
            validator_version=validation.schema_version,
        )
        if not validation.warnings:
            return backend_receipt

        return normalize_receipt(
            accepted=backend_receipt.accepted,
            receipt_id=backend_receipt.receipt_id,
            backend_kind=backend_receipt.backend_kind,
            transport_ref=backend_receipt.transport_ref,
            validator_version=backend_receipt.validator_version,
            warnings=validation.warnings + backend_receipt.warnings,
            errors=backend_receipt.errors,
        )


def send_heartbeat(
    status_payload: HeartbeatStatus | Mapping[str, Any],
) -> SubmitReceipt:
    """Send heartbeat status through the configured SDK runtime."""

    from subsystem_sdk.base.runtime import get_runtime

    return get_runtime().send_heartbeat(status_payload)
