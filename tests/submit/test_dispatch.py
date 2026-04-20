from collections.abc import Mapping
from typing import Any

import pytest

from subsystem_sdk.submit._dispatch import validate_then_dispatch
from subsystem_sdk.submit.receipt import SubmitReceipt
from subsystem_sdk.validate import EX0_SEMANTIC, ValidationResult


def test_dispatch_skips_backend_when_validation_fails() -> None:
    calls: list[Mapping[str, Any]] = []

    def validator(payload: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.fail(
            ex_type="Ex-2",
            schema_version="contracts-v1",
            field_errors=("missing produced_at",),
            warnings=("validator warning",),
        )

    def dispatch(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(payload)
        return {"accepted": True}

    receipt = validate_then_dispatch(
        {"ex_type": "Ex-2"},
        backend_kind="mock",
        validator=validator,
        dispatch=dispatch,
    )

    assert calls == []
    assert receipt.accepted is False
    assert receipt.warnings == ("validator warning",)
    assert receipt.errors == ("missing produced_at",)


def test_dispatch_preserves_backend_rejection_and_warning_order() -> None:
    payload = {"ex_type": "Ex-2"}

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        # Validator sees the FULL payload (including SDK envelope).
        assert received is payload
        return ValidationResult.ok(
            ex_type="Ex-2",
            schema_version="contracts-v2",
            warnings=("validator warning",),
        )

    def dispatch(received: Mapping[str, Any]) -> Mapping[str, Any]:
        # Stage-2.7 follow-up #2 (codex review #2 P1): dispatch receives
        # the WIRE shape (envelope stripped). For a payload that is ONLY
        # envelope (no producer fields), the wire is an empty dict.
        assert received == {}
        assert "ex_type" not in received
        return {
            "accepted": False,
            "receipt_id": "receipt-1",
            "transport_ref": None,
            "warnings": ("backend warning",),
            "errors": ("backend rejected",),
        }

    receipt = validate_then_dispatch(
        payload,
        backend_kind="mock",
        validator=validator,
        dispatch=dispatch,
    )

    assert receipt == SubmitReceipt(
        accepted=False,
        receipt_id="receipt-1",
        backend_kind="mock",
        transport_ref=None,
        validator_version="contracts-v2",
        warnings=("validator warning", "backend warning"),
        errors=("backend rejected",),
    )


def test_dispatch_applies_boundary_check_before_backend_call() -> None:
    calls: list[Mapping[str, Any]] = []
    payload = {"ex_type": "Ex-0", "semantic": "business_event"}

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.ok(ex_type="Ex-0", schema_version="contracts-v3")

    def boundary_check(
        received: Mapping[str, Any], validation: ValidationResult
    ) -> tuple[str, ...]:
        assert validation.ex_type == "Ex-0"
        if received.get("semantic") != EX0_SEMANTIC:
            return ("heartbeat payload semantic mismatch",)
        return ()

    def dispatch(received: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(received)
        return {"accepted": True}

    receipt = validate_then_dispatch(
        payload,
        backend_kind="mock",
        validator=validator,
        dispatch=dispatch,
        boundary_check=boundary_check,
    )

    assert calls == []
    assert receipt.accepted is False
    assert receipt.errors == ("heartbeat payload semantic mismatch",)


def test_dispatch_rejects_backend_private_fields_before_public_receipt() -> None:
    def validator(payload: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.ok(ex_type="Ex-2", schema_version="contracts-v4")

    def dispatch(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"accepted": True, "kafka_topic": "private-topic"}

    with pytest.raises(ValueError, match="kafka_topic"):
        validate_then_dispatch(
            {"ex_type": "Ex-2"},
            backend_kind="full_kafka",
            validator=validator,
            dispatch=dispatch,
        )
