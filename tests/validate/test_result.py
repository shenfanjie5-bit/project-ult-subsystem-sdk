import pytest
from pydantic import ValidationError

from subsystem_sdk.validate import ValidationResult


def test_ok_factory_builds_valid_result() -> None:
    result = ValidationResult.ok(ex_type="Ex-1", schema_version="v0")

    assert result.is_valid is True
    assert result.ex_type == "Ex-1"
    assert result.schema_version == "v0"
    assert result.field_errors == ()
    assert result.warnings == ()
    assert result.preflight is None


def test_ok_factory_preserves_warnings() -> None:
    result = ValidationResult.ok(
        ex_type="Ex-2", schema_version="v0", warnings=["soft warning"]
    )

    assert result.warnings == ("soft warning",)


def test_fail_factory_builds_invalid_result() -> None:
    result = ValidationResult.fail(
        ex_type="Ex-3",
        schema_version="v0",
        field_errors=["field missing"],
        warnings=["soft warning"],
    )

    assert result.is_valid is False
    assert result.ex_type == "Ex-3"
    assert result.field_errors == ("field missing",)
    assert result.warnings == ("soft warning",)


def test_fail_factory_requires_field_errors() -> None:
    with pytest.raises(ValueError, match="require field errors"):
        ValidationResult.fail(ex_type="Ex-1", schema_version="v0", field_errors=[])


def test_valid_result_rejects_field_errors() -> None:
    with pytest.raises(
        ValidationError, match="valid results cannot include field errors"
    ):
        ValidationResult(
            is_valid=True,
            ex_type="Ex-1",
            schema_version="v0",
            field_errors=("x",),
        )


def test_ex_type_must_be_supported() -> None:
    with pytest.raises(ValidationError):
        ValidationResult.ok(ex_type="Ex-9", schema_version="v0")
