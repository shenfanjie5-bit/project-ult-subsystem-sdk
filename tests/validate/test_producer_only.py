from typing import Any

import pytest

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES
from subsystem_sdk.validate import (
    INGEST_METADATA_FIELDS,
    PRODUCER_OWNED_REQUIRED,
    IngestMetadataLeakError,
    MissingProducerFieldError,
    SemanticsError,
    assert_no_ingest_metadata,
    assert_producer_only,
)


EX0_PAYLOAD = {
    "subsystem_id": "subsystem-a",
    "version": "1.0.0",
    "heartbeat_at": "2026-04-17T00:00:00Z",
    "status": "ok",
}


def _payload_with_leak(field: str, nested: bool) -> dict[str, Any]:
    if nested:
        return {**EX0_PAYLOAD, "transport": {field: "backend-owned"}}
    return {**EX0_PAYLOAD, field: "backend-owned"}


def test_ingest_metadata_fields_are_frozen() -> None:
    assert INGEST_METADATA_FIELDS == frozenset(
        {"submitted_at", "ingest_seq", "layer_b_receipt_id"}
    )


def test_producer_owned_required_has_all_supported_ex_types() -> None:
    assert set(PRODUCER_OWNED_REQUIRED) == set(SUPPORTED_EX_TYPES)
    assert len(PRODUCER_OWNED_REQUIRED) == 4


def test_producer_owned_required_cannot_be_mutated_to_bypass_guards() -> None:
    payload = {
        "subsystem_id": "subsystem-a",
        "version": "1.0.0",
        "heartbeat_at": "2026-04-17T00:00:00Z",
    }

    with pytest.raises(TypeError):
        PRODUCER_OWNED_REQUIRED["Ex-0"] = frozenset()

    with pytest.raises(MissingProducerFieldError, match="status"):
        assert_producer_only("Ex-0", payload)


@pytest.mark.parametrize("field", sorted(INGEST_METADATA_FIELDS))
@pytest.mark.parametrize("nested", [False, True], ids=["top_level", "nested"])
def test_assert_no_ingest_metadata_rejects_top_level_and_nested_leaks(
    field: str,
    nested: bool,
) -> None:
    payload = _payload_with_leak(field, nested)

    with pytest.raises(IngestMetadataLeakError, match=field):
        assert_no_ingest_metadata(payload)


def test_assert_producer_only_rejects_unknown_ex_type() -> None:
    with pytest.raises(SemanticsError, match="Unsupported ex_type"):
        assert_producer_only("Ex-9", EX0_PAYLOAD)


def test_assert_producer_only_rejects_missing_required_fields() -> None:
    payload = {
        "subsystem_id": "subsystem-a",
        "version": "1.0.0",
        "heartbeat_at": "2026-04-17T00:00:00Z",
    }

    with pytest.raises(MissingProducerFieldError, match="status"):
        assert_producer_only("Ex-0", payload)


def test_assert_producer_only_accepts_ex0_happy_path() -> None:
    assert_producer_only("Ex-0", EX0_PAYLOAD)


def test_semantics_errors_inherit_from_value_error() -> None:
    assert issubclass(SemanticsError, ValueError)
    assert issubclass(IngestMetadataLeakError, ValueError)
    assert issubclass(MissingProducerFieldError, ValueError)
