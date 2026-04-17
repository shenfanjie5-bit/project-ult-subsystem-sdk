from collections.abc import Mapping
from typing import Any

import pytest

from subsystem_sdk.backends import MockSubmitBackend
from subsystem_sdk.base import (
    BaseSubsystemContext,
    RuntimeNotConfiguredError,
    SubsystemRegistrationSpec,
    configure_runtime,
)
from subsystem_sdk.base.runtime import _clear_runtime_for_tests
from subsystem_sdk.heartbeat import HeartbeatClient, send_heartbeat
from subsystem_sdk.submit import SubmitClient, submit
from subsystem_sdk.validate import EX0_SEMANTIC, ValidationResult


class RecordingHeartbeatBackend:
    backend_kind = "mock"

    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def send(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(payload)
        return {
            "accepted": True,
            "receipt_id": "heartbeat-receipt-1",
            "transport_ref": "heartbeat-transport-1",
            "warnings": (),
            "errors": (),
        }


@pytest.fixture(autouse=True)
def clear_configured_runtime() -> None:
    _clear_runtime_for_tests()
    yield
    _clear_runtime_for_tests()


def _validator(payload: Mapping[str, Any]) -> ValidationResult:
    ex_type = payload["ex_type"]
    assert ex_type in {"Ex-0", "Ex-2"}
    return ValidationResult.ok(
        ex_type=ex_type,  # type: ignore[arg-type]
        schema_version="contracts-v-test",
    )


def _context(
    submit_backend: MockSubmitBackend,
    heartbeat_backend: RecordingHeartbeatBackend,
) -> BaseSubsystemContext:
    registration = SubsystemRegistrationSpec(
        subsystem_id="subsystem-demo",
        version="0.1.0",
        domain="demo",
        supported_ex_types=["Ex-0", "Ex-2"],
        owner="sdk",
        heartbeat_policy_ref="default",
    )
    return BaseSubsystemContext(
        registration=registration,
        submit_client=SubmitClient(submit_backend, validator=_validator),
        heartbeat_client=HeartbeatClient(heartbeat_backend, validator=_validator),
        validator=_validator,
    )


def test_public_submit_and_heartbeat_require_configured_runtime() -> None:
    with pytest.raises(RuntimeNotConfiguredError):
        submit({"ex_type": "Ex-2"})

    with pytest.raises(RuntimeNotConfiguredError):
        send_heartbeat({"status": "healthy"})


def test_public_submit_and_heartbeat_use_configured_context_runtime() -> None:
    submit_backend = MockSubmitBackend(receipt_id="submit-receipt-1")
    heartbeat_backend = RecordingHeartbeatBackend()
    configure_runtime(_context(submit_backend, heartbeat_backend))
    ex2_payload = {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-demo",
        "produced_at": "2026-04-17T00:00:00Z",
    }

    submit_receipt = submit(ex2_payload)
    heartbeat_receipt = send_heartbeat({"status": "healthy", "pending_count": 2})

    assert submit_receipt.accepted is True
    assert submit_receipt.receipt_id == "submit-receipt-1"
    assert submit_backend.submitted_payloads == (ex2_payload,)
    assert heartbeat_receipt.accepted is True
    assert heartbeat_receipt.receipt_id == "heartbeat-receipt-1"
    assert len(heartbeat_backend.calls) == 1
    heartbeat_payload = heartbeat_backend.calls[0]
    assert heartbeat_payload["ex_type"] == "Ex-0"
    assert heartbeat_payload["semantic"] == EX0_SEMANTIC
    assert heartbeat_payload["subsystem_id"] == "subsystem-demo"
    assert heartbeat_payload["version"] == "0.1.0"
    assert heartbeat_payload["status"] == "healthy"
    assert heartbeat_payload["pending_count"] == 2
