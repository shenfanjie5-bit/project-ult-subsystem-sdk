from typing import get_args

import pytest
from pydantic import ValidationError

from subsystem_sdk.submit import (
    BACKEND_KINDS,
    RESERVED_PRIVATE_KEYS,
    BackendKind,
    SubmitReceipt,
    assert_no_private_leak,
    normalize_receipt,
)


def test_construct_valid_receipt() -> None:
    receipt = SubmitReceipt(
        accepted=True,
        receipt_id="receipt-1",
        backend_kind="mock",
        transport_ref=None,
        validator_version="v0",
        warnings=("warn",),
    )

    assert receipt.accepted is True
    assert receipt.receipt_id == "receipt-1"
    assert receipt.backend_kind == "mock"
    assert receipt.warnings == ("warn",)
    assert receipt.errors == ()


def test_accepted_receipt_rejects_errors() -> None:
    with pytest.raises(
        ValidationError, match="accepted receipts cannot include errors"
    ):
        SubmitReceipt(
            accepted=True,
            receipt_id="receipt-1",
            backend_kind="mock",
            validator_version="v0",
            errors=("x",),
        )


def test_backend_kind_must_be_known() -> None:
    with pytest.raises(ValidationError):
        SubmitReceipt(
            accepted=False,
            receipt_id="receipt-1",
            backend_kind="rabbitmq",
            validator_version="v0",
            errors=("rejected",),
        )


def test_backend_kinds_match_literal() -> None:
    assert BACKEND_KINDS == get_args(BackendKind)


def test_normalize_receipt_generates_receipt_id() -> None:
    receipt = normalize_receipt(
        accepted=True,
        backend_kind="mock",
        transport_ref=None,
        validator_version="v0",
    )

    assert len(receipt.receipt_id) == 32
    assert int(receipt.receipt_id, 16) >= 0
    assert receipt.accepted is True
    assert receipt.warnings == ()
    assert receipt.errors == ()


def test_normalize_receipt_preserves_explicit_receipt_id_and_tuples() -> None:
    receipt = normalize_receipt(
        accepted=False,
        backend_kind="lite_pg",
        transport_ref="transport-1",
        validator_version="v0",
        warnings=["warn"],
        errors=["failed"],
        receipt_id="receipt-1",
    )

    assert receipt.receipt_id == "receipt-1"
    assert receipt.backend_kind == "lite_pg"
    assert receipt.transport_ref == "transport-1"
    assert receipt.warnings == ("warn",)
    assert receipt.errors == ("failed",)


def test_normalize_receipt_rejects_empty_explicit_receipt_id() -> None:
    with pytest.raises(ValidationError):
        normalize_receipt(
            accepted=True,
            backend_kind="mock",
            transport_ref=None,
            validator_version="v0",
            receipt_id="",
        )


def test_assert_no_private_leak_rejects_reserved_keys() -> None:
    with pytest.raises(ValueError, match="kafka_topic"):
        assert_no_private_leak({"kafka_topic": "topic-a"})


def test_assert_no_private_leak_allows_public_keys() -> None:
    assert_no_private_leak({"accepted": True, "receipt_id": "receipt-1"})


def test_reserved_private_keys_are_fixed() -> None:
    assert RESERVED_PRIVATE_KEYS == frozenset(
        {"pg_queue_id", "kafka_topic", "kafka_offset", "kafka_partition"}
    )


def test_submit_receipt_is_frozen() -> None:
    receipt = normalize_receipt(
        accepted=True,
        backend_kind="mock",
        transport_ref=None,
        validator_version="v0",
    )

    with pytest.raises((ValidationError, TypeError)):
        receipt.accepted = False
