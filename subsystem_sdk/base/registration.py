"""Subsystem registration metadata and in-memory registry."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES
from subsystem_sdk.validate.result import ExType


class RegistrationError(ValueError):
    """Raised when registration metadata conflicts with an existing entry."""


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze_value(item) for item in value)
    return deepcopy(value)


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw_value(item) for item in value]
    if isinstance(value, frozenset | set):
        return [_thaw_value(item) for item in value]
    return value


class SubsystemRegistrationSpec(BaseModel):
    """Stable registration metadata for a producer subsystem."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subsystem_id: str
    version: str
    domain: str
    supported_ex_types: tuple[ExType, ...]
    owner: str
    heartbeat_policy_ref: str
    capabilities: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator(
        "subsystem_id",
        "version",
        "domain",
        "owner",
        "heartbeat_policy_ref",
    )
    @classmethod
    def _string_fields_must_be_non_empty(cls, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("registration string fields must be strings")
        if not value.strip():
            raise ValueError("registration string fields must be non-empty")
        return value

    @field_validator("supported_ex_types", mode="before")
    @classmethod
    def _coerce_supported_ex_types(cls, value: Any) -> tuple[Any, ...]:
        if isinstance(value, (str, bytes)):
            raise TypeError("supported_ex_types must be a sequence of Ex types")
        try:
            coerced = tuple(value)
        except TypeError as exc:
            raise TypeError(
                "supported_ex_types must be a sequence of Ex types"
            ) from exc

        unsupported = [
            ex_type for ex_type in coerced if ex_type not in SUPPORTED_EX_TYPES
        ]
        if unsupported:
            joined = ", ".join(repr(ex_type) for ex_type in unsupported)
            raise ValueError(f"unsupported Ex type(s): {joined}")
        return coerced

    @field_validator("capabilities", mode="before")
    @classmethod
    def _copy_capabilities(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("capabilities must be a mapping")
        return deepcopy(dict(value))

    @field_validator("capabilities")
    @classmethod
    def _freeze_capabilities(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return _freeze_value(value)

    @field_serializer("capabilities")
    def _serialize_capabilities(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return _thaw_value(value)


class RegistrationRegistry:
    """Metadata-only registry for subsystem registration specs."""

    def __init__(self) -> None:
        self._specs: dict[str, SubsystemRegistrationSpec] = {}

    def register(self, spec: SubsystemRegistrationSpec) -> None:
        existing = self._specs.get(spec.subsystem_id)
        if existing is None:
            self._specs[spec.subsystem_id] = spec
            return

        if existing == spec:
            return

        differing_fields = [
            field_name
            for field_name in (
                "version",
                "domain",
                "owner",
                "supported_ex_types",
                "heartbeat_policy_ref",
                "capabilities",
            )
            if getattr(existing, field_name) != getattr(spec, field_name)
        ]
        fields = ", ".join(differing_fields)
        raise RegistrationError(
            "subsystem registration already exists with different metadata: "
            f"{spec.subsystem_id!r}; differing field(s): {fields}"
        )

    def get(self, subsystem_id: str) -> SubsystemRegistrationSpec | None:
        return self._specs.get(subsystem_id)

    def clear(self) -> None:
        self._specs.clear()


_DEFAULT_REGISTRY = RegistrationRegistry()


def register_subsystem(
    spec: SubsystemRegistrationSpec,
    *,
    registry: RegistrationRegistry | None = None,
) -> None:
    """Register subsystem metadata in the provided or default registry."""

    (registry or _DEFAULT_REGISTRY).register(spec)


def get_registered_subsystem(
    subsystem_id: str,
    *,
    registry: RegistrationRegistry | None = None,
) -> SubsystemRegistrationSpec | None:
    """Return registered subsystem metadata, if present."""

    return (registry or _DEFAULT_REGISTRY).get(subsystem_id)
