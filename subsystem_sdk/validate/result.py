"""Validation result model shared by local validators."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_serializer,
    field_validator,
)

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES

ExType = Literal["Ex-0", "Ex-1", "Ex-2", "Ex-3"]
_EX_TYPE_VALUES: Final[tuple[str, ...]] = get_args(ExType)

if _EX_TYPE_VALUES != SUPPORTED_EX_TYPES:  # pragma: no cover - import-time guard.
    raise RuntimeError("ValidationResult ExType must match SUPPORTED_EX_TYPES")


def _coerce_diagnostics(value: Sequence[str], *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")

    coerced = tuple(value)
    if not all(isinstance(item, str) for item in coerced):
        raise TypeError(f"{field_name} must contain only strings")
    return coerced


def _freeze_preflight(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            frozen[key] = _freeze_preflight(item)
        elif isinstance(item, list | tuple):
            frozen[key] = tuple(item)
        elif isinstance(item, set | frozenset):
            frozen[key] = frozenset(item)
        else:
            frozen[key] = item
    return MappingProxyType(frozen)


def _thaw_preflight(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_preflight(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_thaw_preflight(item) for item in value]
    if isinstance(value, set | frozenset):
        return [_thaw_preflight(item) for item in sorted(value, key=repr)]
    return value


class ValidationResult(BaseModel):
    """Stable local validation result returned before submit."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    ex_type: ExType
    schema_version: str
    field_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    preflight: Mapping[str, Any] | None = None

    @field_validator("field_errors", "warnings", mode="before")
    @classmethod
    def _coerce_diagnostic_fields(
        cls, value: Sequence[str], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _coerce_diagnostics(value, field_name=info.field_name)

    @field_validator("preflight")
    @classmethod
    def _freeze_preflight_field(
        cls, preflight: Mapping[str, Any] | None
    ) -> Mapping[str, Any] | None:
        if preflight is None:
            return None
        return _freeze_preflight(preflight)

    @field_serializer("preflight")
    def _serialize_preflight_field(
        self, preflight: Mapping[str, Any] | None
    ) -> dict[str, Any] | None:
        if preflight is None:
            return None
        return _thaw_preflight(preflight)

    @field_validator("field_errors")
    @classmethod
    def _valid_results_have_no_field_errors(
        cls, field_errors: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        if info.data.get("is_valid") is True and field_errors:
            raise ValueError("valid results cannot include field errors")
        return field_errors

    @classmethod
    def ok(
        cls,
        ex_type: ExType,
        schema_version: str,
        *,
        warnings: Sequence[str] = (),
        preflight: Mapping[str, Any] | None = None,
    ) -> "ValidationResult":
        return cls(
            is_valid=True,
            ex_type=ex_type,
            schema_version=schema_version,
            warnings=_coerce_diagnostics(warnings, field_name="warnings"),
            preflight=preflight,
        )

    @classmethod
    def fail(
        cls,
        ex_type: ExType,
        schema_version: str,
        *,
        field_errors: Sequence[str],
        warnings: Sequence[str] = (),
        preflight: Mapping[str, Any] | None = None,
    ) -> "ValidationResult":
        coerced_errors = _coerce_diagnostics(
            field_errors, field_name="field_errors"
        )
        if not coerced_errors:
            raise ValueError("failed validation results require field errors")
        return cls(
            is_valid=False,
            ex_type=ex_type,
            schema_version=schema_version,
            field_errors=coerced_errors,
            warnings=_coerce_diagnostics(warnings, field_name="warnings"),
            preflight=preflight,
        )
