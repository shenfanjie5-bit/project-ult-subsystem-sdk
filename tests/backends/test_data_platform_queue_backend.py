from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from subsystem_sdk.backends import DataPlatformQueueSubmitBackend
from subsystem_sdk.submit import normalize_backend_receipt
from subsystem_sdk.validate import ValidationResult


def test_data_platform_queue_prepares_candidate_queue_envelope() -> None:
    backend = DataPlatformQueueSubmitBackend()

    prepared = backend.prepare_dispatch_payload(
        {
            "subsystem_id": "subsystem-a",
            "signal_id": "signal-1",
        },
        ValidationResult.ok(ex_type="Ex-3", schema_version="contracts-v1"),
    )

    assert prepared == {
        "payload_type": "Ex-3",
        "submitted_by": "subsystem-a",
        "subsystem_id": "subsystem-a",
        "signal_id": "signal-1",
    }


@pytest.mark.parametrize(
    "reserved_field",
    [
        "payload_type",
        "submitted_by",
        "submitted_at",
        "ingest_seq",
        "layer_b_receipt_id",
        "ex_type",
        "semantic",
        "produced_at",
    ],
)
def test_data_platform_queue_preparer_rejects_reserved_wire_fields(
    reserved_field: str,
) -> None:
    backend = DataPlatformQueueSubmitBackend()

    with pytest.raises(ValueError, match="reserved field"):
        backend.prepare_dispatch_payload(
            {
                "subsystem_id": "subsystem-a",
                reserved_field: "leak",
            },
            ValidationResult.ok(ex_type="Ex-2", schema_version="contracts-v1"),
        )


@pytest.mark.parametrize("subsystem_id", [None, "", "   ", 12])
def test_data_platform_queue_preparer_requires_subsystem_id(
    subsystem_id: object,
) -> None:
    backend = DataPlatformQueueSubmitBackend()

    with pytest.raises(ValueError, match="subsystem_id"):
        backend.prepare_dispatch_payload(
            {"subsystem_id": subsystem_id},
            ValidationResult.ok(ex_type="Ex-1", schema_version="contracts-v1"),
        )


def test_data_platform_queue_submit_uses_injected_submit_candidate() -> None:
    calls: list[dict[str, Any]] = []

    def submit_candidate(payload):
        calls.append(dict(payload))
        return SimpleNamespace(id=42, ingest_seq=99)

    backend = DataPlatformQueueSubmitBackend(submit_candidate_func=submit_candidate)
    receipt = backend.submit(
        {
            "payload_type": "Ex-1",
            "submitted_by": "subsystem-a",
            "subsystem_id": "subsystem-a",
        }
    )

    assert calls == [
        {
            "payload_type": "Ex-1",
            "submitted_by": "subsystem-a",
            "subsystem_id": "subsystem-a",
        }
    ]
    assert receipt == {
        "accepted": True,
        "transport_ref": "42",
        "warnings": (),
        "errors": (),
    }
    public = normalize_backend_receipt(
        receipt,
        backend_kind="data_platform_queue",
        validator_version="contracts-v1",
    )
    assert public.backend_kind == "data_platform_queue"
    assert public.transport_ref == "42"


def test_data_platform_queue_submit_accepts_mapping_candidate_item() -> None:
    backend = DataPlatformQueueSubmitBackend(
        submit_candidate_func=lambda payload: {"id": "candidate-77"},
    )

    receipt = backend.submit(
        {
            "payload_type": "Ex-1",
            "submitted_by": "subsystem-a",
            "subsystem_id": "subsystem-a",
        }
    )

    assert receipt["accepted"] is True
    assert receipt["transport_ref"] == "candidate-77"


def test_data_platform_queue_submit_hides_backend_failure_details() -> None:
    def submit_candidate(payload):
        raise RuntimeError(
            "sql failed on data_platform.candidate_queue with ingest_seq=99"
        )

    backend = DataPlatformQueueSubmitBackend(submit_candidate_func=submit_candidate)
    receipt = backend.submit(
        {
            "payload_type": "Ex-2",
            "submitted_by": "subsystem-a",
            "subsystem_id": "subsystem-a",
        }
    )

    assert receipt["accepted"] is False
    assert receipt["transport_ref"] is None
    assert receipt["warnings"] == ()
    assert receipt["errors"] == ("data_platform_queue submit failed",)
    assert "sql" not in receipt["errors"][0]
    assert "data_platform.candidate_queue" not in receipt["errors"][0]
    assert "ingest_seq" not in receipt["errors"][0]
