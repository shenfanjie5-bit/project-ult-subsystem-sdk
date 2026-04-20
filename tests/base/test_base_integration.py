from collections.abc import Mapping
from typing import Any

from subsystem_sdk.backends import MockSubmitBackend
from subsystem_sdk.base import (
    BaseSubsystemContext,
    RegistrationRegistry,
    SubsystemRegistrationSpec,
    get_registered_subsystem,
    register_subsystem,
)
from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.submit import SubmitClient
from subsystem_sdk.validate import ValidationResult


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


def _validator(payload: Mapping[str, Any]) -> ValidationResult:
    ex_type = payload["ex_type"]
    assert ex_type in {"Ex-0", "Ex-1"}
    return ValidationResult.ok(
        ex_type=ex_type,  # type: ignore[arg-type]
        schema_version="contracts-v-test",
    )


def test_base_context_register_submit_and_heartbeat_happy_path() -> None:
    registry = RegistrationRegistry()
    registration = SubsystemRegistrationSpec(
        subsystem_id="subsystem-demo",
        version="0.1.0",
        domain="demo",
        supported_ex_types=["Ex-0", "Ex-1"],
        owner="sdk",
        heartbeat_policy_ref="default",
    )
    register_subsystem(registration, registry=registry)

    submit_backend = MockSubmitBackend(receipt_id="submit-receipt-1")
    heartbeat_backend = RecordingHeartbeatBackend()
    context = BaseSubsystemContext(
        registration=registration,
        submit_client=SubmitClient(submit_backend, validator=_validator),
        heartbeat_client=HeartbeatClient(heartbeat_backend, validator=_validator),
        validator=_validator,
    )
    ex1_payload = {
        "ex_type": "Ex-1",
        "subsystem_id": "subsystem-demo",
        "produced_at": "2026-04-17T00:00:00Z",
    }

    submit_receipt = context.submit(ex1_payload)
    heartbeat_receipt = context.send_heartbeat({"status": "healthy"})

    assert get_registered_subsystem("subsystem-demo", registry=registry) == registration
    assert submit_receipt.accepted is True
    assert submit_receipt.receipt_id == "submit-receipt-1"
    # Stage-2.7 follow-up #2: validate_then_dispatch strips SDK envelope
    # (ex_type/semantic/produced_at) before backend dispatch, so backends
    # see the wire shape contracts.schemas.Ex* validates + Layer B accepts.
    assert submit_backend.submitted_payloads == (
        {"subsystem_id": "subsystem-demo"},
    )
    assert heartbeat_receipt.accepted is True
    assert heartbeat_receipt.receipt_id == "heartbeat-receipt-1"
    # Heartbeat backend must NOT receive ex_type either — pure wire shape.
    assert "ex_type" not in heartbeat_backend.calls[0]
    assert heartbeat_backend.calls[0]["subsystem_id"] == "subsystem-demo"
