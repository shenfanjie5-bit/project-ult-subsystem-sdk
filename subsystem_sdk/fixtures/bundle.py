"""Pydantic models for packaged contract example bundles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from subsystem_sdk._json import freeze_json_like, to_json_safe
from subsystem_sdk.validate.result import ExType


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
        return freeze_json_like(payload)

    @field_serializer("payload")
    def _serialize_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return to_json_safe(payload)


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

    @model_validator(mode="after")
    def _valid_examples_match_bundle_ex_type(self) -> Self:
        mismatched = [
            example.name
            for example in self.valid_examples
            if example.payload.get("ex_type") != self.ex_type
        ]
        if mismatched:
            joined = ", ".join(repr(name) for name in mismatched)
            raise ValueError(
                "valid example payload ex_type must match bundle ex_type "
                f"{self.ex_type!r}; mismatched example(s): {joined}"
            )
        return self
