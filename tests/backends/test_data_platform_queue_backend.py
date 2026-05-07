from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

import subsystem_sdk.backends.data_platform_queue as data_platform_queue_module
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


def test_data_platform_queue_idempotent_required_uses_idempotent_submit() -> None:
    legacy_calls: list[dict[str, Any]] = []
    idempotent_calls: list[dict[str, Any]] = []

    def submit_candidate(payload):
        legacy_calls.append(dict(payload))
        return SimpleNamespace(id="legacy-candidate")

    def submit_candidate_idempotent(payload):
        idempotent_calls.append(dict(payload))
        return SimpleNamespace(candidate_id=123, replayed=False)

    backend = DataPlatformQueueSubmitBackend(
        submit_candidate_func=submit_candidate,
        submit_candidate_idempotent_func=submit_candidate_idempotent,
        idempotent_required=True,
    )
    receipt = backend.submit(
        {
            "payload_type": "Ex-3",
            "submitted_by": "subsystem-holdings",
            "subsystem_id": "subsystem-holdings",
            "delta_id": "delta-1",
        }
    )

    assert legacy_calls == []
    assert idempotent_calls == [
        {
            "payload_type": "Ex-3",
            "submitted_by": "subsystem-holdings",
            "subsystem_id": "subsystem-holdings",
            "delta_id": "delta-1",
        }
    ]
    assert receipt == {
        "accepted": True,
        "transport_ref": "123",
        "warnings": (),
        "errors": (),
    }


def test_data_platform_queue_idempotent_required_missing_api_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_calls: list[dict[str, Any]] = []

    def submit_candidate(payload):
        legacy_calls.append(dict(payload))
        return SimpleNamespace(id="legacy-candidate")

    monkeypatch.setattr(
        data_platform_queue_module,
        "import_module",
        lambda name: SimpleNamespace(submit_candidate=submit_candidate),
    )
    backend = DataPlatformQueueSubmitBackend(
        submit_candidate_func=submit_candidate,
        idempotent_required=True,
    )

    receipt = backend.submit(
        {
            "payload_type": "Ex-3",
            "submitted_by": "subsystem-holdings",
            "subsystem_id": "subsystem-holdings",
            "delta_id": "delta-1",
        }
    )

    assert legacy_calls == []
    assert receipt == {
        "accepted": False,
        "transport_ref": None,
        "warnings": (),
        "errors": ("data_platform_queue submit failed",),
    }


def test_data_platform_queue_idempotent_safe_receipt_maps_without_private_leak() -> None:
    class SafeReceipt:
        candidate_id = 321
        replayed = True

        def as_public_dict(self) -> dict[str, Any]:
            return {
                "candidate_id": self.candidate_id,
                "payload_type": "Ex-3",
                "submitted_by": "subsystem-holdings",
                "submitted_at": datetime.now(UTC).isoformat(),
                "ingest_seq": 456,
                "validation_status": "pending",
                "rejection_reason": None,
                "replayed": self.replayed,
                "payload": {"provider_payload": "must-not-leak"},
                "raw_payload_path": "/tmp/private.json",
            }

    backend = DataPlatformQueueSubmitBackend(
        submit_candidate_idempotent_func=lambda payload: SafeReceipt(),
        idempotent_required=True,
    )

    receipt = backend.submit(
        {
            "payload_type": "Ex-3",
            "submitted_by": "subsystem-holdings",
            "subsystem_id": "subsystem-holdings",
            "delta_id": "delta-1",
        }
    )

    assert receipt == {
        "accepted": True,
        "transport_ref": "321",
        "warnings": ("data_platform_queue idempotent replay",),
        "errors": (),
    }
    for private_key in (
        "candidate_id",
        "payload",
        "provider_payload",
        "raw_payload_path",
        "ingest_seq",
        "submitted_at",
        "validation_status",
        "rejection_reason",
        "replayed",
    ):
        assert private_key not in receipt

    public = normalize_backend_receipt(
        receipt,
        backend_kind="data_platform_queue",
        validator_version="contracts-v1",
    )
    assert public.transport_ref == "321"
    assert public.warnings == ("data_platform_queue idempotent replay",)


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
