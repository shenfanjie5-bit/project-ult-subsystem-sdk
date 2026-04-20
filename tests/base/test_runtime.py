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
from subsystem_sdk.base.runtime import (
    RuntimeAlreadyConfiguredError,
    _clear_runtime_for_tests,
)
from subsystem_sdk.heartbeat import HeartbeatClient, send_heartbeat
from subsystem_sdk.submit import SubmitClient, submit
from subsystem_sdk.validate import EX0_SEMANTIC, ValidationResult


class RecordingHeartbeatBackend:
    backend_kind = "mock"

    def __init__(
        self,
        *,
        receipt_id: str = "heartbeat-receipt-1",
        transport_ref: str = "heartbeat-transport-1",
    ) -> None:
        self.receipt_id = receipt_id
        self.transport_ref = transport_ref
        self.calls: list[Mapping[str, Any]] = []

    def send(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(payload)
        return {
            "accepted": True,
            "receipt_id": self.receipt_id,
            "transport_ref": self.transport_ref,
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
    *,
    subsystem_id: str = "subsystem-demo",
    version: str = "0.1.0",
) -> BaseSubsystemContext:
    registration = SubsystemRegistrationSpec(
        subsystem_id=subsystem_id,
        version=version,
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
    ex2_payload = {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-demo",
        "produced_at": "2026-04-17T00:00:00Z",
    }

    with configure_runtime(_context(submit_backend, heartbeat_backend)):
        submit_receipt = submit(ex2_payload)
        heartbeat_receipt = send_heartbeat(
            {"status": "healthy", "pending_count": 2}
        )

    assert submit_receipt.accepted is True
    assert submit_receipt.receipt_id == "submit-receipt-1"
    # Stage-2.7 follow-up #2: backend gets WIRE shape (envelope stripped).
    assert submit_backend.submitted_payloads == (
        {"subsystem_id": "subsystem-demo"},
    )
    assert heartbeat_receipt.accepted is True
    assert heartbeat_receipt.receipt_id == "heartbeat-receipt-1"
    assert len(heartbeat_backend.calls) == 1
    heartbeat_payload = heartbeat_backend.calls[0]
    # Heartbeat backend receives wire shape — no SDK envelope, status mapped.
    assert "ex_type" not in heartbeat_payload
    assert "semantic" not in heartbeat_payload
    assert heartbeat_payload["subsystem_id"] == "subsystem-demo"
    assert heartbeat_payload["version"] == "0.1.0"
    # SDK "healthy" -> contracts wire "ok".
    assert heartbeat_payload["status"] == "ok"
    assert heartbeat_payload["pending_count"] == 2


def test_configure_runtime_is_scoped_and_does_not_mutate_process_global() -> None:
    submit_backend = MockSubmitBackend(receipt_id="submit-receipt-1")
    heartbeat_backend = RecordingHeartbeatBackend()
    context = _context(submit_backend, heartbeat_backend)
    ex2_payload = {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-demo",
        "produced_at": "2026-04-17T00:00:00Z",
    }

    configure_runtime(context)
    with pytest.raises(RuntimeNotConfiguredError):
        submit(ex2_payload)

    with configure_runtime(context):
        assert submit(ex2_payload).receipt_id == "submit-receipt-1"

    with pytest.raises(RuntimeNotConfiguredError):
        send_heartbeat({"status": "healthy"})


def test_scoped_runtime_rejects_nested_reroute_between_subsystems() -> None:
    submit_backend_a = MockSubmitBackend(receipt_id="submit-a")
    heartbeat_backend_a = RecordingHeartbeatBackend(receipt_id="heartbeat-a")
    context_a = _context(
        submit_backend_a,
        heartbeat_backend_a,
        subsystem_id="subsystem-a",
        version="1.0.0",
    )
    submit_backend_b = MockSubmitBackend(receipt_id="submit-b")
    heartbeat_backend_b = RecordingHeartbeatBackend(receipt_id="heartbeat-b")
    context_b = _context(
        submit_backend_b,
        heartbeat_backend_b,
        subsystem_id="subsystem-b",
        version="2.0.0",
    )
    payload_a = {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-a",
        "produced_at": "2026-04-17T00:00:00Z",
    }
    payload_b = {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-b",
        "produced_at": "2026-04-17T00:00:00Z",
    }

    with configure_runtime(context_a):
        assert submit(payload_a).receipt_id == "submit-a"
        assert send_heartbeat({"status": "healthy"}).receipt_id == "heartbeat-a"

        with pytest.raises(RuntimeAlreadyConfiguredError):
            with configure_runtime(context_b):
                submit(payload_b)
                send_heartbeat({"status": "degraded"})

    with configure_runtime(context_b):
        assert submit(payload_b).receipt_id == "submit-b"
        assert send_heartbeat({"status": "degraded"}).receipt_id == "heartbeat-b"

    # Stage-2.7 follow-up #2: backends receive wire shape (envelope stripped).
    assert submit_backend_a.submitted_payloads == (
        {"subsystem_id": "subsystem-a"},
    )
    assert submit_backend_b.submitted_payloads == (
        {"subsystem_id": "subsystem-b"},
    )
    assert len(heartbeat_backend_a.calls) == 1
    assert len(heartbeat_backend_b.calls) == 1
    assert heartbeat_backend_a.calls[0]["subsystem_id"] == "subsystem-a"
    assert heartbeat_backend_b.calls[0]["subsystem_id"] == "subsystem-b"
