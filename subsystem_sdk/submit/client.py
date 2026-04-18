"""Unified submit client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from subsystem_sdk.submit._dispatch import validate_then_dispatch
from subsystem_sdk.submit.protocol import SubmitBackendInterface
from subsystem_sdk.submit.receipt import SubmitReceipt
from subsystem_sdk.validate.engine import (
    _apply_preflight,
    validate_payload,
)
from subsystem_sdk.validate.preflight import (
    EntityRegistryLookup,
    PreflightPolicy,
    run_entity_preflight,
    should_run_entity_preflight,
)
from subsystem_sdk.validate.result import ValidationResult

if TYPE_CHECKING:
    from subsystem_sdk.backends.config import SubmitBackendConfig


def _default_backend_factory(
    config: SubmitBackendConfig,
) -> SubmitBackendInterface:
    from subsystem_sdk.backends.factory import build_submit_backend

    return build_submit_backend(config)


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

    @classmethod
    def from_config(
        cls,
        config: SubmitBackendConfig,
        *,
        backend_factory: Callable[
            [SubmitBackendConfig], SubmitBackendInterface
        ] = _default_backend_factory,
        validator: Callable[[Mapping[str, Any]], ValidationResult] = validate_payload,
        entity_lookup: EntityRegistryLookup | None = None,
        preflight_policy: PreflightPolicy = "skip",
    ) -> "SubmitClient":
        """Build a submit client from backend config and a backend factory.

        Full backends that need live transport objects, such as Kafka producers,
        should pass ``backend_factory`` to keep dependency injection explicit.
        """

        return cls(
            backend_factory(config),
            validator=validator,
            entity_lookup=entity_lookup,
            preflight_policy=preflight_policy,
        )

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        return validate_then_dispatch(
            payload,
            backend_kind=self._backend.backend_kind,
            validator=self._validator,
            dispatch=self._backend.submit,
            enrich_validation=self._enrich_validation,
        )

    def _enrich_validation(
        self,
        payload: Mapping[str, Any],
        validation: ValidationResult,
    ) -> ValidationResult:
        if validation.preflight is None and should_run_entity_preflight(
            is_valid=validation.is_valid,
            ex_type=validation.ex_type,
            policy=self._preflight_policy,
        ):
            preflight = run_entity_preflight(
                payload,
                lookup=self._entity_lookup,
                policy=self._preflight_policy,
            )
            return _apply_preflight(validation, preflight)
        return validation


def submit(payload: Mapping[str, Any]) -> SubmitReceipt:
    """Submit a producer payload through the configured SDK runtime."""

    from subsystem_sdk.base.runtime import get_runtime

    return get_runtime().submit(payload)
