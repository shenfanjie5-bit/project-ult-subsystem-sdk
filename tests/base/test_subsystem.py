from collections.abc import Mapping
from pathlib import Path
from typing import Any

from subsystem_sdk.base.subsystem import BaseSubsystem
from subsystem_sdk.submit import SubmitReceipt
from subsystem_sdk.validate import ValidationResult


class RecordingContext:
    def __init__(self) -> None:
        self.validate_calls: list[Mapping[str, Any]] = []
        self.submit_calls: list[Mapping[str, Any]] = []
        self.heartbeat_calls: list[Mapping[str, Any]] = []
        self.validation = ValidationResult.ok(
            ex_type="Ex-1",
            schema_version="contracts-v1",
        )
        self.submit_receipt = SubmitReceipt(
            accepted=True,
            receipt_id="submit-receipt",
            backend_kind="mock",
            transport_ref=None,
            validator_version="contracts-v1",
        )
        self.heartbeat_receipt = SubmitReceipt(
            accepted=True,
            receipt_id="heartbeat-receipt",
            backend_kind="mock",
            transport_ref=None,
            validator_version="contracts-v1",
        )

    def validate_payload(self, payload: Mapping[str, Any]) -> ValidationResult:
        self.validate_calls.append(payload)
        return self.validation

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        self.submit_calls.append(payload)
        return self.submit_receipt

    def send_heartbeat(self, status: Mapping[str, Any]) -> SubmitReceipt:
        self.heartbeat_calls.append(status)
        return self.heartbeat_receipt


def test_base_subsystem_validate_is_context_wrapper() -> None:
    context = RecordingContext()
    subsystem = BaseSubsystem(context)  # type: ignore[arg-type]
    payload = {"ex_type": "Ex-1"}

    result = subsystem.validate(payload)

    assert result is context.validation
    assert context.validate_calls == [payload]


def test_base_subsystem_submit_is_context_wrapper() -> None:
    context = RecordingContext()
    subsystem = BaseSubsystem(context)  # type: ignore[arg-type]
    payload = {"ex_type": "Ex-1"}

    receipt = subsystem.submit(payload)

    assert receipt is context.submit_receipt
    assert context.submit_calls == [payload]


def test_base_subsystem_heartbeat_is_context_wrapper() -> None:
    context = RecordingContext()
    subsystem = BaseSubsystem(context)  # type: ignore[arg-type]
    status = {"status": "healthy"}

    receipt = subsystem.heartbeat(status)

    assert receipt is context.heartbeat_receipt
    assert context.heartbeat_calls == [status]


def test_base_source_has_no_domain_specific_business_terms(PROJECT_ROOT: Path) -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "subsystem_sdk" / "base").glob("*.py"))
    )

    for term in ("新闻", "公告", "研报"):
        assert term not in source
