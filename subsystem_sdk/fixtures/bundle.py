"""Pydantic models for packaged contract example bundles."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_serializer,
    field_validator,
)

from subsystem_sdk.validate.result import ExType


def _freeze_json_like(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json_like(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_json_like(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze_json_like(item) for item in value)
    return value


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, frozenset | set):
        return [_to_json_safe(item) for item in sorted(value, key=repr)]
    return value


class ContractExample(BaseModel):
    """One producer-owned payload example plus its contract-test notes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    payload: Mapping[str, Any]
    notes: str

    @field_validator("name", "notes")
    @classmethod
    def _require_non_empty_text(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must be non-empty")
        return value

    @field_validator("payload")
    @classmethod
    def _require_non_empty_payload(
        cls, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if not payload:
            raise ValueError("payload must be non-empty")
        return _freeze_json_like(payload)

    @field_serializer("payload")
    def _serialize_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return _to_json_safe(payload)


class ContractExampleBundle(BaseModel):
    """Reusable examples for one Ex type, shared by SDK tests and scaffolds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle_name: str
    ex_type: ExType
    valid_examples: tuple[ContractExample, ...]
    invalid_examples: tuple[ContractExample, ...]
    notes: str = ""

    @field_validator("bundle_name")
    @classmethod
    def _require_non_empty_bundle_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bundle_name must be non-empty")
        return value
