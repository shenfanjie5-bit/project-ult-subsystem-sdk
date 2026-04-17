import sys
import types
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.base.runtime import _clear_runtime_for_tests, configure_runtime
from subsystem_sdk.heartbeat import HeartbeatClient, send_heartbeat
from subsystem_sdk.submit import SubmitReceipt
from subsystem_sdk.validate import EX0_SEMANTIC, ValidationResult


class Ex1BusinessPayload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1-business"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    produced_at: str


def _install_ex1_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {"Ex-1": Ex1BusinessPayload}
    monkeypatch.setitem(sys.modules, "contracts", module)


class RecordingHeartbeatBackend:
    backend_kind = "mock"

    def __init__(
        self,
        receipt: Mapping[str, Any] | SubmitReceipt | None = None,
    ) -> None:
        self.calls: list[Mapping[str, Any]] = []
        self._receipt = receipt or {
            "accepted": True,
            "receipt_id": "heartbeat-receipt-1",
            "transport_ref": "heartbeat-transport-1",
            "warnings": ("backend warning",),
            "errors": (),
        }

    def send(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | SubmitReceipt:
        self.calls.append(payload)
        return self._receipt


def test_heartbeat_client_validates_before_calling_backend() -> None:
    payload = {
        "ex_type": "Ex-0",
        "semantic": EX0_SEMANTIC,
        "subsystem_id": "subsystem-a",
    }
    backend = RecordingHeartbeatBackend()

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        assert received is payload
        return ValidationResult.ok(
            ex_type="Ex-0",
            schema_version="contracts-v1",
            warnings=("validator warning",),
        )

    receipt = HeartbeatClient(backend, validator=validator).send_heartbeat(payload)

    assert backend.calls == [payload]
    assert receipt == SubmitReceipt(
        accepted=True,
        receipt_id="heartbeat-receipt-1",
        backend_kind="mock",
        transport_ref="heartbeat-transport-1",
        validator_version="contracts-v1",
        warnings=("validator warning", "backend warning"),
    )


def test_heartbeat_client_does_not_call_backend_when_validation_fails() -> None:
    backend = RecordingHeartbeatBackend()

    def validator(payload: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.fail(
            ex_type="Ex-0",
            schema_version="contracts-v2",
            field_errors=("missing heartbeat_at",),
            warnings=("validator warning",),
        )

    receipt = HeartbeatClient(backend, validator=validator).send_heartbeat(
        {"ex_type": "Ex-0"}
    )

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.backend_kind == "mock"
    assert receipt.validator_version == "contracts-v2"
    assert receipt.warnings == ("validator warning",)
    assert receipt.errors == ("missing heartbeat_at",)


def test_heartbeat_client_preserves_backend_rejection() -> None:
    backend = RecordingHeartbeatBackend(
        {
            "accepted": False,
            "receipt_id": "heartbeat-receipt-2",
            "transport_ref": "heartbeat-transport-2",
            "warnings": (),
            "errors": ("backend rejected heartbeat",),
        }
    )

    def validator(payload: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.ok(ex_type="Ex-0", schema_version="contracts-v3")

    receipt = HeartbeatClient(backend, validator=validator).send_heartbeat(
        {"ex_type": "Ex-0", "semantic": EX0_SEMANTIC}
    )

    assert backend.calls == [{"ex_type": "Ex-0", "semantic": EX0_SEMANTIC}]
    assert receipt.accepted is False
    assert receipt.validator_version == "contracts-v3"
    assert receipt.errors == ("backend rejected heartbeat",)


def test_heartbeat_client_uses_validation_schema_version_for_backend_receipt() -> None:
    backend = RecordingHeartbeatBackend(
        SubmitReceipt(
            accepted=True,
            receipt_id="heartbeat-receipt-3",
            backend_kind="mock",
            transport_ref="heartbeat-transport-3",
            validator_version="backend-version",
        )
    )

    def validator(payload: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.ok(ex_type="Ex-0", schema_version="contracts-v4")

    receipt = HeartbeatClient(backend, validator=validator).send_heartbeat(
        {"ex_type": "Ex-0", "semantic": EX0_SEMANTIC}
    )

    assert receipt.validator_version == "contracts-v4"


def test_heartbeat_client_rejects_valid_non_ex0_payload_without_backend_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ex1_contracts(monkeypatch)
    backend = RecordingHeartbeatBackend()
    payload = {
        "ex_type": "Ex-1",
        "subsystem_id": "subsystem-a",
        "produced_at": "2026-04-17T00:00:00Z",
    }

    receipt = HeartbeatClient(backend).send_heartbeat(payload)

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.validator_version == "v-ex1-business"
    assert any("heartbeat validator result" in error for error in receipt.errors)
    assert any("heartbeat payload ex_type" in error for error in receipt.errors)


def test_heartbeat_client_requires_fixed_ex0_semantic_after_validation() -> None:
    backend = RecordingHeartbeatBackend()
    payload = {"ex_type": "Ex-0", "semantic": "business_event"}

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        assert received is payload
        return ValidationResult.ok(ex_type="Ex-0", schema_version="contracts-v5")

    receipt = HeartbeatClient(backend, validator=validator).send_heartbeat(payload)

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.validator_version == "contracts-v5"
    assert receipt.errors == (
        "heartbeat payload semantic must be "
        f"{EX0_SEMANTIC!r}; got 'business_event'",
    )


def test_module_send_heartbeat_uses_configured_runtime() -> None:
    _clear_runtime_for_tests()
    payload = {"status": "healthy"}
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

        def send_heartbeat(self, received: Mapping[str, Any]) -> SubmitReceipt:
            self.calls.append(received)
            return expected

    runtime = Runtime()

    with configure_runtime(runtime):
        assert send_heartbeat(payload) is expected
        assert runtime.calls == [payload]


def test_heartbeat_client_keeps_ex0_business_semantic_rejection_on_path() -> None:
    backend = RecordingHeartbeatBackend()
    payload = {
        "ex_type": "Ex-0",
        "subsystem_id": "subsystem-a",
        "version": "1.0.0",
        "heartbeat_at": "2026-04-17T00:00:00Z",
        "status": "healthy",
        "business_event": "trade",
    }

    receipt = HeartbeatClient(backend).send_heartbeat(payload)

    assert backend.calls == []
    assert receipt.accepted is False
    assert any("non-heartbeat" in error for error in receipt.errors)
