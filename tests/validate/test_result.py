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


def test_ok_factory_preserves_preflight_without_generating_ids() -> None:
    result = ValidationResult.ok(
        ex_type="Ex-2",
        schema_version="v0",
        preflight={"checked": True, "warnings": ["entity unresolved"]},
    )

    assert result.preflight == {"checked": True, "warnings": ("entity unresolved",)}
    assert "canonical_entity_id" not in result.preflight


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


def test_fail_factory_preserves_preflight_without_generating_ids() -> None:
    result = ValidationResult.fail(
        ex_type="Ex-3",
        schema_version="v0",
        field_errors=["field missing"],
        preflight={"entity_ref": "tmp-1"},
    )

    assert result.preflight == {"entity_ref": "tmp-1"}
    assert "canonical_entity_id" not in result.preflight


def test_preflight_mapping_is_immutable() -> None:
    result = ValidationResult.ok(
        ex_type="Ex-1",
        schema_version="v0",
        preflight={"nested": {"value": 1}},
    )

    with pytest.raises(TypeError):
        result.preflight["new"] = "value"  # type: ignore[index]

    with pytest.raises(TypeError):
        result.preflight["nested"]["value"] = 2  # type: ignore[index]


def test_fail_factory_requires_field_errors() -> None:
    with pytest.raises(ValueError, match="require field errors"):
        ValidationResult.fail(ex_type="Ex-1", schema_version="v0", field_errors=[])


@pytest.mark.parametrize("warnings", ("abc", b"abc"))
def test_ok_factory_rejects_raw_string_warnings(warnings: object) -> None:
    with pytest.raises(TypeError, match="warnings"):
        ValidationResult.ok(
            ex_type="Ex-1",
            schema_version="v0",
            warnings=warnings,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("field_errors", ("abc", b"abc"))
def test_fail_factory_rejects_raw_string_field_errors(field_errors: object) -> None:
    with pytest.raises(TypeError, match="field_errors"):
        ValidationResult.fail(
            ex_type="Ex-1",
            schema_version="v0",
            field_errors=field_errors,  # type: ignore[arg-type]
        )


def test_factory_rejects_non_string_diagnostics() -> None:
    with pytest.raises(TypeError, match="warnings"):
        ValidationResult.ok(
            ex_type="Ex-1",
            schema_version="v0",
            warnings=["ok", 123],  # type: ignore[list-item]
        )


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
