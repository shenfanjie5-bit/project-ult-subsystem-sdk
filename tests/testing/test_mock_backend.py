from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.submit import SubmitClient
from subsystem_sdk.testing import BackendEvent, MockBackend
from subsystem_sdk.validate import EX0_SEMANTIC, ValidationResult


def _validator(payload):
    return ValidationResult.ok(
        ex_type=payload["ex_type"],
        schema_version=f"schema-{payload['ex_type']}",
    )


def test_mock_backend_drives_submit_and_heartbeat_clients() -> None:
    backend = MockBackend()

    heartbeat_receipt = HeartbeatClient(backend, validator=_validator).send_heartbeat(
        {"ex_type": "Ex-0", "semantic": EX0_SEMANTIC, "nested": {"value": 1}}
    )
    submit_receipt = SubmitClient(backend, validator=_validator).submit(
        {"ex_type": "Ex-2", "nested": {"value": 2}}
    )

    assert heartbeat_receipt.accepted is True
    assert heartbeat_receipt.backend_kind == "mock"
    assert submit_receipt.accepted is True
    assert submit_receipt.backend_kind == "mock"
    assert tuple(event.kind for event in backend.events) == ("heartbeat", "submit")


def test_mock_backend_records_defensive_event_copies() -> None:
    backend = MockBackend()
    heartbeat_payload = {
        "ex_type": "Ex-0",
        "semantic": EX0_SEMANTIC,
        "nested": {"value": 1},
    }
    submit_payload = {"ex_type": "Ex-1", "nested": {"value": 2}}

    backend.send(heartbeat_payload)
    backend.submit(submit_payload)
    heartbeat_payload["nested"]["value"] = 10
    submit_payload["nested"]["value"] = 20

    assert backend.events == (
        BackendEvent(
            kind="heartbeat",
            payload={
                "ex_type": "Ex-0",
                "semantic": EX0_SEMANTIC,
                "nested": {"value": 1},
            },
        ),
        BackendEvent(
            kind="submit",
            payload={"ex_type": "Ex-1", "nested": {"value": 2}},
        ),
    )
    assert backend.heartbeat_payloads == (
        {
            "ex_type": "Ex-0",
            "semantic": EX0_SEMANTIC,
            "nested": {"value": 1},
        },
    )

    returned_payload = backend.heartbeat_payloads[0]
    returned_payload["nested"]["value"] = 99

    assert backend.heartbeat_payloads[0]["nested"]["value"] == 1
