from collections.abc import Mapping
from typing import Any

from subsystem_sdk.base.runtime import _clear_runtime_for_tests, configure_runtime
from subsystem_sdk.submit import SubmitClient, SubmitReceipt, submit
from subsystem_sdk.validate import ValidationResult


class RecordingBackend:
    backend_kind = "mock"

    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(payload)
        return {
            "accepted": True,
            "receipt_id": "backend-receipt-1",
            "transport_ref": "backend-transport-1",
            "warnings": ("backend warning",),
            "errors": (),
        }


def test_submit_client_validates_before_calling_backend() -> None:
    payload = {"ex_type": "Ex-2", "subsystem_id": "subsystem-a"}
    backend = RecordingBackend()

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        assert received is payload
        return ValidationResult.ok(
            ex_type="Ex-2",
            schema_version="contracts-v1",
            warnings=("validator warning",),
        )

    receipt = SubmitClient(backend, validator=validator).submit(payload)

    assert backend.calls == [payload]
    assert receipt == SubmitReceipt(
        accepted=True,
        receipt_id="backend-receipt-1",
        backend_kind="mock",
        transport_ref="backend-transport-1",
        validator_version="contracts-v1",
        warnings=("validator warning", "backend warning"),
    )


def test_submit_client_does_not_call_backend_when_validation_fails() -> None:
    backend = RecordingBackend()

    def validator(payload: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.fail(
            ex_type="Ex-2",
            schema_version="contracts-v2",
            field_errors=("missing produced_at",),
            warnings=("validator warning",),
        )

    receipt = SubmitClient(backend, validator=validator).submit({"ex_type": "Ex-2"})

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.backend_kind == "mock"
    assert receipt.validator_version == "contracts-v2"
    assert receipt.warnings == ("validator warning",)
    assert receipt.errors == ("missing produced_at",)


def test_module_submit_uses_configured_runtime() -> None:
    _clear_runtime_for_tests()
    payload = {"ex_type": "Ex-1"}
    expected = SubmitReceipt(
        accepted=True,
        receipt_id="receipt-1",
        backend_kind="mock",
        transport_ref=None,
        validator_version="contracts-v1",
    )

    class Runtime:
        def __init__(self) -> None:
            self.calls: list[Mapping[str, Any]] = []

        def submit(self, received: Mapping[str, Any]) -> SubmitReceipt:
            self.calls.append(received)
            return expected

    runtime = Runtime()
    configure_runtime(runtime)

    try:
        assert submit(payload) is expected
        assert runtime.calls == [payload]
    finally:
        _clear_runtime_for_tests()
