from subsystem_sdk.backends import MockSubmitBackend


def test_mock_backend_stores_payload_copies() -> None:
    backend = MockSubmitBackend()
    payload = {"ex_type": "Ex-2", "nested": {"value": 1}}

    receipt = backend.submit(payload)
    payload["nested"]["value"] = 2

    assert receipt["accepted"] is True
    assert backend.submitted_payloads[0] == {
        "ex_type": "Ex-2",
        "nested": {"value": 1},
    }
    assert backend.submitted_payloads[0] is not payload


def test_mock_backend_returns_raw_receipt_without_private_keys() -> None:
    receipt = MockSubmitBackend(receipt_id="receipt-1").submit({"ex_type": "Ex-1"})

    assert receipt == {
        "accepted": True,
        "receipt_id": "receipt-1",
        "transport_ref": "mock-1",
        "warnings": (),
        "errors": (),
    }
    assert "pg_queue_id" not in receipt
    assert "kafka_topic" not in receipt
