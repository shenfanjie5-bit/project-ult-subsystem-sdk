import pytest

from subsystem_sdk.validate import (
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
    return {"subsystem_id": "subsystem-a", "produced_at": "2026-04-17T00:00:00Z"}


def test_ingest_metadata_fields_are_fixed() -> None:
    assert INGEST_METADATA_FIELDS == frozenset(
        {"submitted_at", "ingest_seq", "layer_b_receipt_id"}
    )


def test_ex0_semantic_constant_is_fixed() -> None:
    assert EX0_SEMANTIC == "metadata_or_heartbeat"


def test_producer_owned_required_covers_supported_ex_types() -> None:
    assert set(PRODUCER_OWNED_REQUIRED) == {"Ex-0", "Ex-1", "Ex-2", "Ex-3"}


@pytest.mark.parametrize("field_name", sorted(INGEST_METADATA_FIELDS))
def test_assert_producer_only_rejects_top_level_ingest_metadata(
    field_name: str,
) -> None:
    payload = _ex1_payload() | {field_name: "ingest-owned"}

    with pytest.raises(IngestMetadataLeakError, match=field_name):
        assert_producer_only("Ex-1", payload)


@pytest.mark.parametrize("field_name", sorted(INGEST_METADATA_FIELDS))
def test_assert_producer_only_rejects_nested_ingest_metadata(field_name: str) -> None:
    payload = _ex1_payload() | {"nested": {field_name: "ingest-owned"}}

    with pytest.raises(IngestMetadataLeakError, match=field_name):
        assert_producer_only("Ex-1", payload)


def test_assert_producer_only_rejects_missing_required_fields() -> None:
    with pytest.raises(MissingProducerFieldError, match="produced_at"):
        assert_producer_only("Ex-2", {"subsystem_id": "subsystem-a"})


def test_assert_producer_only_accepts_ex0_happy_path() -> None:
    assert_producer_only(
        "Ex-0",
        {
            "subsystem_id": "subsystem-a",
            "version": "1.0.0",
            "heartbeat_at": "2026-04-17T00:00:00Z",
            "status": "ok",
        },
    )


def test_assert_producer_only_rejects_unknown_ex_type() -> None:
    with pytest.raises(SemanticsError, match="unsupported Ex type"):
        assert_producer_only("Ex-9", _ex1_payload())


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
