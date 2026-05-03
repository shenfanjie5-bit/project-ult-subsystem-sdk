from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from subsystem_sdk.backends import (
    DataPlatformQueueSubmitBackend,
    SubmitBackendHeartbeatAdapter,
)
from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.submit import SubmitClient
from subsystem_sdk.validate import EX0_SEMANTIC, ValidationResult


def test_submit_client_bridges_ex_payloads_to_data_platform_queue_envelope() -> None:
    calls: list[dict[str, Any]] = []

    def submit_candidate(payload):
        calls.append(dict(payload))
        return SimpleNamespace(id=len(calls))

    def validator(payload):
        return ValidationResult.ok(
            ex_type=payload["ex_type"],
            schema_version="contracts-v-test",
        )

    backend = DataPlatformQueueSubmitBackend(submit_candidate_func=submit_candidate)
    client = SubmitClient(backend, validator=validator)

    for ex_type in ("Ex-1", "Ex-2", "Ex-3"):
        receipt = client.submit(
            {
                "ex_type": ex_type,
                "produced_at": "2026-05-03T00:00:00Z",
                "subsystem_id": "bridge-test",
                "payload_value": ex_type,
            }
        )
        assert receipt.accepted is True
        assert receipt.backend_kind == "data_platform_queue"

    assert calls == [
        {
            "payload_type": "Ex-1",
            "submitted_by": "bridge-test",
            "subsystem_id": "bridge-test",
            "payload_value": "Ex-1",
        },
        {
            "payload_type": "Ex-2",
            "submitted_by": "bridge-test",
            "subsystem_id": "bridge-test",
            "payload_value": "Ex-2",
        },
        {
            "payload_type": "Ex-3",
            "submitted_by": "bridge-test",
            "subsystem_id": "bridge-test",
            "payload_value": "Ex-3",
        },
    ]


def test_heartbeat_client_bridges_ex0_to_data_platform_queue_envelope() -> None:
    calls: list[dict[str, Any]] = []

    def submit_candidate(payload):
        calls.append(dict(payload))
        return SimpleNamespace(id=99)

    def validator(payload):
        return ValidationResult.ok(ex_type="Ex-0", schema_version="contracts-v-test")

    submit_backend = DataPlatformQueueSubmitBackend(
        submit_candidate_func=submit_candidate,
    )
    heartbeat_client = HeartbeatClient(
        SubmitBackendHeartbeatAdapter(submit_backend),
        validator=validator,
    )

    receipt = heartbeat_client.send_heartbeat(
        {
            "ex_type": "Ex-0",
            "semantic": EX0_SEMANTIC,
            "subsystem_id": "bridge-test",
            "status": "ok",
        }
    )

    assert receipt.accepted is True
    assert receipt.backend_kind == "data_platform_queue"
    assert calls == [
        {
            "payload_type": "Ex-0",
            "submitted_by": "bridge-test",
            "subsystem_id": "bridge-test",
            "status": "ok",
        }
    ]
