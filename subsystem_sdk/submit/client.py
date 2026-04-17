"""Unified submit client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from subsystem_sdk.submit.protocol import SubmitBackendInterface
from subsystem_sdk.submit.receipt import (
    SubmitReceipt,
    normalize_backend_receipt,
    normalize_receipt,
)
from subsystem_sdk.validate.engine import (
    _apply_preflight,
    _should_run_preflight,
    validate_payload,
)
from subsystem_sdk.validate.preflight import (
    EntityRegistryLookup,
    PreflightPolicy,
    run_entity_preflight,
)
from subsystem_sdk.validate.result import ValidationResult


class SubmitClient:
    """Validate producer payloads before delegating to a submit backend."""

    def __init__(
        self,
        backend: SubmitBackendInterface,
        validator: Callable[[Mapping[str, Any]], ValidationResult] = validate_payload,
        *,
        entity_lookup: EntityRegistryLookup | None = None,
        preflight_policy: PreflightPolicy = "skip",
    ) -> None:
        self._backend = backend
        self._validator = validator
        self._entity_lookup = entity_lookup
        self._preflight_policy = preflight_policy

    @property
    def backend(self) -> SubmitBackendInterface:
        return self._backend

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        validation = self._validator(payload)
        if _should_run_preflight(validation, self._preflight_policy):
            preflight = run_entity_preflight(
                payload,
                lookup=self._entity_lookup,
                policy=self._preflight_policy,
            )
            validation = _apply_preflight(validation, preflight)

        if validation.is_valid is False:
            return normalize_receipt(
                accepted=False,
                backend_kind=self._backend.backend_kind,
                transport_ref=None,
                validator_version=validation.schema_version,
                warnings=validation.warnings,
                errors=validation.field_errors,
            )

        backend_receipt = normalize_backend_receipt(
            self._backend.submit(payload),
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


def submit(payload: Mapping[str, Any]) -> SubmitReceipt:
    """Submit a producer payload through the configured SDK runtime."""

    from subsystem_sdk.base.runtime import get_runtime

    return get_runtime().submit(payload)
