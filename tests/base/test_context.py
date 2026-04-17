from collections.abc import Mapping
from typing import Any

from subsystem_sdk.base.context import BaseSubsystemContext
from subsystem_sdk.base.registration import SubsystemRegistrationSpec
from subsystem_sdk.heartbeat import HeartbeatStatus
from subsystem_sdk.submit import SubmitReceipt
from subsystem_sdk.validate import EX0_SEMANTIC, ValidationResult


class RecordingSubmitClient:
    def __init__(self, receipt: SubmitReceipt) -> None:
        self.calls: list[Mapping[str, Any]] = []
        self._receipt = receipt

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        self.calls.append(payload)
        return self._receipt


class RecordingHeartbeatClient:
    def __init__(self, receipt: SubmitReceipt) -> None:
        self.calls: list[Mapping[str, Any]] = []
        self._receipt = receipt

    def send_heartbeat(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        self.calls.append(payload)
        return self._receipt


def _registration() -> SubsystemRegistrationSpec:
    return SubsystemRegistrationSpec(
        subsystem_id="subsystem-demo",
        version="0.1.0",
        domain="demo",
        supported_ex_types=["Ex-0", "Ex-1"],
        owner="sdk",
        heartbeat_policy_ref="default",
    )


def _context(
    *,
    submit_client: RecordingSubmitClient | None = None,
    heartbeat_client: RecordingHeartbeatClient | None = None,
) -> BaseSubsystemContext:
    return BaseSubsystemContext(
        registration=_registration(),
        submit_client=submit_client
        or RecordingSubmitClient(
            SubmitReceipt(
                accepted=True,
                receipt_id="submit-receipt",
                backend_kind="mock",
                transport_ref=None,
                validator_version="contracts-v1",
            )
        ),  # type: ignore[arg-type]
        heartbeat_client=heartbeat_client
        or RecordingHeartbeatClient(
            SubmitReceipt(
                accepted=True,
                receipt_id="heartbeat-receipt",
                backend_kind="mock",
                transport_ref=None,
                validator_version="contracts-v1",
            )
        ),  # type: ignore[arg-type]
    )


def test_context_validate_payload_uses_configured_validator() -> None:
    payload = {"ex_type": "Ex-1"}
    expected = ValidationResult.ok(ex_type="Ex-1", schema_version="contracts-v1")
    calls: list[Mapping[str, Any]] = []

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        calls.append(received)
        return expected

    context = BaseSubsystemContext(
        registration=_registration(),
        submit_client=RecordingSubmitClient(
            SubmitReceipt(
                accepted=True,
                receipt_id="submit-receipt",
                backend_kind="mock",
                transport_ref=None,
                validator_version="contracts-v1",
            )
        ),  # type: ignore[arg-type]
        heartbeat_client=RecordingHeartbeatClient(
            SubmitReceipt(
                accepted=True,
                receipt_id="heartbeat-receipt",
                backend_kind="mock",
                transport_ref=None,
                validator_version="contracts-v1",
            )
        ),  # type: ignore[arg-type]
        validator=validator,
    )

    assert context.validate_payload(payload) is expected
    assert calls == [payload]


def test_context_submit_delegates_to_submit_client() -> None:
    expected = SubmitReceipt(
        accepted=True,
        receipt_id="submit-receipt",
        backend_kind="mock",
        transport_ref="transport-1",
        validator_version="contracts-v1",
    )
    submit_client = RecordingSubmitClient(expected)
    context = _context(submit_client=submit_client)
    payload = {"ex_type": "Ex-1"}

    receipt = context.submit(payload)

    assert receipt is expected
    assert submit_client.calls == [payload]


def test_context_send_heartbeat_builds_ex0_payload_and_delegates() -> None:
    expected = SubmitReceipt(
        accepted=True,
        receipt_id="heartbeat-receipt",
        backend_kind="mock",
        transport_ref="transport-2",
        validator_version="contracts-v1",
    )
    heartbeat_client = RecordingHeartbeatClient(expected)
    context = _context(heartbeat_client=heartbeat_client)

    receipt = context.send_heartbeat(HeartbeatStatus(status="healthy"))

    assert receipt is expected
    assert len(heartbeat_client.calls) == 1
    payload = heartbeat_client.calls[0]
    assert payload["ex_type"] == "Ex-0"
    assert payload["semantic"] == EX0_SEMANTIC
    assert payload["subsystem_id"] == "subsystem-demo"
    assert payload["version"] == "0.1.0"
    assert payload["status"] == "healthy"


def test_context_send_heartbeat_accepts_status_mapping() -> None:
    heartbeat_client = RecordingHeartbeatClient(
        SubmitReceipt(
            accepted=True,
            receipt_id="heartbeat-receipt",
            backend_kind="mock",
            transport_ref=None,
            validator_version="contracts-v1",
        )
    )
    context = _context(heartbeat_client=heartbeat_client)

    context.send_heartbeat({"status": "degraded", "pending_count": 3})

    assert heartbeat_client.calls[0]["status"] == "degraded"
    assert heartbeat_client.calls[0]["pending_count"] == 3
