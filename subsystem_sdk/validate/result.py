"""Validation result model shared by local validators."""

from __future__ import annotations

from typing import Any, Final, Literal, Sequence, get_args

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES

ExType = Literal["Ex-0", "Ex-1", "Ex-2", "Ex-3"]
_EX_TYPE_VALUES: Final[tuple[str, ...]] = get_args(ExType)

if _EX_TYPE_VALUES != SUPPORTED_EX_TYPES:  # pragma: no cover - import-time guard.
    raise RuntimeError("ValidationResult ExType must match SUPPORTED_EX_TYPES")


class ValidationResult(BaseModel):
    """Stable local validation result returned before submit."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    ex_type: ExType
    schema_version: str
    field_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    preflight: dict[str, Any] | None = None

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
    ) -> "ValidationResult":
        return cls(
            is_valid=True,
            ex_type=ex_type,
            schema_version=schema_version,
            warnings=tuple(warnings),
        )

    @classmethod
    def fail(
        cls,
        ex_type: ExType,
        schema_version: str,
        *,
        field_errors: Sequence[str],
        warnings: Sequence[str] = (),
    ) -> "ValidationResult":
        if not field_errors:
            raise ValueError("failed validation results require field errors")
        return cls(
            is_valid=False,
            ex_type=ex_type,
            schema_version=schema_version,
            field_errors=tuple(field_errors),
            warnings=tuple(warnings),
        )
