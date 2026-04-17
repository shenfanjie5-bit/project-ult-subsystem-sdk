import pytest

from subsystem_sdk.validate import (
    EX0_BANNED_SEMANTICS,
    EX0_SEMANTIC,
    INGEST_METADATA_FIELDS,
    PRODUCER_OWNED_REQUIRED,
    Ex0SemanticError,
    IngestMetadataLeakError,
    MissingProducerFieldError,
    SemanticsError,
    assert_ex0_semantic,
    assert_producer_only,
)


def _ex1_payload() -> dict[str, object]:
    return {
        "ex_type": "Ex-1",
        "subsystem_id": "subsystem-a",
        "produced_at": "2026-04-17T00:00:00Z",
    }


def _ex0_payload() -> dict[str, object]:
    return {
        "ex_type": "Ex-0",
        "subsystem_id": "subsystem-a",
        "version": "1.0.0",
        "heartbeat_at": "2026-04-17T00:00:00Z",
        "status": "ok",
    }


def test_ingest_metadata_fields_are_fixed() -> None:
    assert INGEST_METADATA_FIELDS == frozenset(
        {"submitted_at", "ingest_seq", "layer_b_receipt_id"}
    )


def test_ex0_semantic_constant_is_fixed() -> None:
    assert EX0_SEMANTIC == "metadata_or_heartbeat"


def test_producer_owned_required_covers_supported_ex_types() -> None:
    assert set(PRODUCER_OWNED_REQUIRED) == {"Ex-0", "Ex-1", "Ex-2", "Ex-3"}


def test_producer_owned_required_cannot_be_mutated_to_disable_checks() -> None:
    with pytest.raises(TypeError):
        PRODUCER_OWNED_REQUIRED["Ex-2"] = frozenset({"subsystem_id"})  # type: ignore[index]

    with pytest.raises(MissingProducerFieldError, match="produced_at"):
        assert_producer_only({"ex_type": "Ex-2", "subsystem_id": "subsystem-a"})


@pytest.mark.parametrize("field_name", sorted(INGEST_METADATA_FIELDS))
def test_assert_producer_only_rejects_top_level_ingest_metadata(
    field_name: str,
) -> None:
    payload = _ex1_payload() | {field_name: "ingest-owned"}

    with pytest.raises(IngestMetadataLeakError, match=field_name):
        assert_producer_only(payload)


@pytest.mark.parametrize("field_name", sorted(INGEST_METADATA_FIELDS))
def test_assert_producer_only_rejects_nested_ingest_metadata(field_name: str) -> None:
    payload = _ex1_payload() | {"nested": {field_name: "ingest-owned"}}

    with pytest.raises(IngestMetadataLeakError, match=field_name):
        assert_producer_only(payload)


def test_assert_producer_only_rejects_missing_required_fields() -> None:
    with pytest.raises(MissingProducerFieldError, match="produced_at"):
        assert_producer_only({"ex_type": "Ex-2", "subsystem_id": "subsystem-a"})


def test_assert_producer_only_accepts_ex0_happy_path() -> None:
    assert_producer_only(_ex0_payload())


def test_assert_producer_only_accepts_ex0_explicit_fixed_semantic() -> None:
    assert_producer_only(_ex0_payload() | {"semantic": EX0_SEMANTIC})


@pytest.mark.parametrize("declared_semantic", sorted(EX0_BANNED_SEMANTICS))
def test_assert_producer_only_rejects_ex0_business_semantic(
    declared_semantic: str,
) -> None:
    payload = _ex0_payload() | {"semantic": declared_semantic}

    with pytest.raises(Ex0SemanticError, match=declared_semantic):
        assert_producer_only(payload)


def test_assert_producer_only_rejects_ex0_non_string_semantic() -> None:
    payload = _ex0_payload() | {"semantic": ["business_event"]}

    with pytest.raises(Ex0SemanticError, match="business_event"):
        assert_producer_only(payload)


def test_assert_producer_only_rejects_ex0_business_field_without_semantic() -> None:
    payload = _ex0_payload() | {"business_event": "trade"}

    with pytest.raises(Ex0SemanticError, match="business_event"):
        assert_producer_only(payload)


def test_assert_producer_only_accepts_legacy_ex0_shape_without_ex_type() -> None:
    payload = _ex0_payload()
    payload.pop("ex_type")

    assert_producer_only(payload)


def test_assert_producer_only_rejects_unknown_ex_type() -> None:
    with pytest.raises(SemanticsError, match="unsupported Ex type"):
        assert_producer_only(_ex1_payload() | {"ex_type": "Ex-9"})


def test_assert_producer_only_uses_payload_ex_type_over_explicit_type() -> None:
    with pytest.raises(SemanticsError, match="does not match payload ex_type"):
        assert_producer_only(_ex0_payload(), ex_type="Ex-1")


def test_assert_producer_only_rejects_legacy_explicit_type_mismatch() -> None:
    with pytest.raises(SemanticsError, match="does not match payload ex_type"):
        assert_producer_only("Ex-1", _ex0_payload())


def test_assert_producer_only_rejects_ex0_shape_declared_as_ex1() -> None:
    payload = _ex0_payload() | {"ex_type": "Ex-1"}

    with pytest.raises(SemanticsError, match="looks like 'Ex-0'"):
        assert_producer_only(payload)


def test_assert_producer_only_rejects_produced_shape_declared_as_ex0() -> None:
    payload = _ex1_payload() | {"ex_type": "Ex-0"}

    with pytest.raises(SemanticsError, match="looks like 'Ex-1/2/3'"):
        assert_producer_only(payload)


def test_exception_hierarchy_inherits_value_error() -> None:
    for error_type in (
        SemanticsError,
        Ex0SemanticError,
        IngestMetadataLeakError,
        MissingProducerFieldError,
    ):
        assert issubclass(error_type, ValueError)


def test_assert_ex0_semantic_rejects_non_banned_unknown_semantic() -> None:
    with pytest.raises(Ex0SemanticError, match="workflow"):
        assert_ex0_semantic("workflow")
