import pytest
from pydantic import ValidationError

from subsystem_sdk.submit import (
    SubmitReceipt,
    normalize_backend_receipt,
    normalize_receipt,
)


def test_normalize_backend_receipt_builds_public_receipt() -> None:
    receipt = normalize_backend_receipt(
        {
            "accepted": True,
            "receipt_id": "receipt-1",
            "transport_ref": "transport-1",
            "warnings": ["queued"],
            "errors": [],
        },
        backend_kind="lite_pg",
        validator_version="contracts-v1",
    )

    assert receipt == SubmitReceipt(
        accepted=True,
        receipt_id="receipt-1",
        backend_kind="lite_pg",
        transport_ref="transport-1",
        validator_version="contracts-v1",
        warnings=("queued",),
    )


def test_normalize_backend_receipt_rejects_pg_private_keys() -> None:
    with pytest.raises(ValueError, match="pg_queue_id"):
        normalize_backend_receipt(
            {"accepted": True, "pg_queue_id": "1"},
            backend_kind="lite_pg",
            validator_version="contracts-v1",
        )


def test_normalize_backend_receipt_rejects_kafka_private_keys() -> None:
    with pytest.raises(ValueError, match="kafka_topic"):
        normalize_backend_receipt(
            {"accepted": True, "kafka_topic": "topic-a"},
            backend_kind="full_kafka",
            validator_version="contracts-v1",
        )


def test_normalize_backend_receipt_rejects_unknown_adapter_fields() -> None:
    with pytest.raises(ValueError, match="sql"):
        normalize_backend_receipt(
            {"accepted": True, "sql": "insert into private_table"},
            backend_kind="lite_pg",
            validator_version="contracts-v1",
        )


def test_submit_receipt_model_rejects_private_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SubmitReceipt.model_validate(
            {
                "accepted": True,
                "receipt_id": "receipt-1",
                "backend_kind": "mock",
                "validator_version": "contracts-v1",
                "kafka_topic": "topic-a",
            }
        )


def test_normalize_receipt_wraps_single_warning_string() -> None:
    receipt = normalize_receipt(
        accepted=True,
        backend_kind="mock",
        transport_ref=None,
        validator_version="contracts-v1",
        warnings="abc",
    )

    assert receipt.warnings == ("abc",)


def test_normalize_receipt_wraps_single_error_string() -> None:
    receipt = normalize_receipt(
        accepted=False,
        backend_kind="mock",
        transport_ref=None,
        validator_version="contracts-v1",
        errors="abc",
    )

    assert receipt.errors == ("abc",)


def test_submit_receipt_public_dump_has_only_section_9_fields() -> None:
    receipt = normalize_receipt(
        accepted=True,
        backend_kind="mock",
        transport_ref="transport-1",
        validator_version="contracts-v1",
        warnings=("warn",),
    )

    assert set(receipt.model_dump()) == {
        "accepted",
        "receipt_id",
        "backend_kind",
        "transport_ref",
        "validator_version",
        "warnings",
        "errors",
    }
