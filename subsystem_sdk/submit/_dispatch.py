"""Shared validate-then-dispatch orchestration for submit-like clients."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from subsystem_sdk.submit.receipt import (
    BackendKind,
    SubmitReceipt,
    normalize_backend_receipt,
    normalize_receipt,
)
from subsystem_sdk.validate.engine import strip_sdk_envelope
from subsystem_sdk.validate.result import ValidationResult

BackendDispatch = Callable[[Mapping[str, Any]], Mapping[str, Any] | SubmitReceipt]
BoundaryCheck = Callable[[Mapping[str, Any], ValidationResult], Sequence[str]]
ValidationEnricher = Callable[[Mapping[str, Any], ValidationResult], ValidationResult]
Validator = Callable[[Mapping[str, Any]], ValidationResult]


def _validation_failure_receipt(
    validation: ValidationResult,
    *,
    backend_kind: BackendKind,
) -> SubmitReceipt:
    return normalize_receipt(
        accepted=False,
        backend_kind=backend_kind,
        transport_ref=None,
        validator_version=validation.schema_version,
        warnings=validation.warnings,
        errors=validation.field_errors,
    )


def _merge_validation_warnings(
    validation: ValidationResult,
    backend_receipt: SubmitReceipt,
) -> SubmitReceipt:
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


def validate_then_dispatch(
    payload: Mapping[str, Any],
    *,
    backend_kind: BackendKind,
    validator: Validator,
    dispatch: BackendDispatch,
    enrich_validation: ValidationEnricher | None = None,
    boundary_check: BoundaryCheck | None = None,
) -> SubmitReceipt:
    """Validate a payload, optionally enforce policy, then normalize receipt."""

    validation = validator(payload)
    if enrich_validation is not None:
        validation = enrich_validation(payload, validation)

    if validation.is_valid is False:
        return _validation_failure_receipt(validation, backend_kind=backend_kind)

    # boundary_check runs against the ORIGINAL payload because it inspects
    # SDK envelope fields (ex_type, semantic) for routing checks (e.g.
    # HeartbeatClient verifies semantic == EX0_SEMANTIC). These fields are
    # then stripped before backend dispatch.
    boundary_errors = (
        tuple(boundary_check(payload, validation))
        if boundary_check is not None
        else ()
    )
    if boundary_errors:
        return normalize_receipt(
            accepted=False,
            backend_kind=backend_kind,
            transport_ref=None,
            validator_version=validation.schema_version,
            warnings=validation.warnings,
            errors=boundary_errors,
        )

    # Strip SDK envelope before dispatch — what reaches the backend
    # (Lite PG queue, Full Kafka topic, MockSubmitBackend, ...) MUST be
    # the wire shape Layer B's contracts.schemas.Ex* model accepts. Without
    # this strip, backends serialize the SDK envelope to the wire and
    # Layer B ingest rejects the payload (codex stage-2.7 review #2 P1).
    wire_payload = strip_sdk_envelope(payload)

    backend_receipt = normalize_backend_receipt(
        dispatch(wire_payload),
        backend_kind=backend_kind,
        validator_version=validation.schema_version,
    )
    return _merge_validation_warnings(validation, backend_receipt)
