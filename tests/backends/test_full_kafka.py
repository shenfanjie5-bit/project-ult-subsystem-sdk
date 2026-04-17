from typing import Any

import pytest
from pydantic import ValidationError

from subsystem_sdk.backends import (
    KafkaBrokerAck,
    KafkaCompatibleSubmitBackend,
    SubmitBackendConfig,
)
from subsystem_sdk.backends.full_kafka import _transport_ref_from_ack
from subsystem_sdk.submit import SubmitReceipt, normalize_backend_receipt


class FakeProducer:
    def __init__(self, ack: KafkaBrokerAck | dict[str, Any]) -> None:
        self.ack = ack
        self.calls: list[tuple[str, bytes, str | None]] = []

    def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str | None = None,
    ) -> KafkaBrokerAck | dict[str, Any]:
        self.calls.append((topic, payload, key))
        return self.ack


class FailingProducer:
    def __init__(self) -> None:
        self.calls = 0

    def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str | None = None,
    ) -> KafkaBrokerAck:
        self.calls += 1
        raise RuntimeError("broker unavailable")


def test_full_kafka_config_accepts_topic_and_is_frozen() -> None:
    config = SubmitBackendConfig(
        backend_kind="full_kafka",
        topic="candidate-events",
    )

    assert config.topic == "candidate-events"
    assert config.delivery_timeout_ms == 1000
    with pytest.raises((ValidationError, TypeError)):
        config.topic = "other-topic"


def test_full_kafka_config_requires_topic() -> None:
    with pytest.raises(ValidationError, match="topic"):
        SubmitBackendConfig(backend_kind="full_kafka")


def test_full_kafka_backend_rejects_wrong_backend_kind_without_producer_call() -> None:
    producer = FakeProducer(KafkaBrokerAck(message_id="m-1"))

    with pytest.raises(ValueError, match="full_kafka"):
        KafkaCompatibleSubmitBackend(
            SubmitBackendConfig(backend_kind="lite_pg"),
            producer,
        )

    assert producer.calls == []


def test_full_kafka_backend_rejects_missing_topic_from_constructed_config() -> None:
    config = SubmitBackendConfig.model_construct(backend_kind="full_kafka", topic=None)

    with pytest.raises(ValueError, match="topic"):
        KafkaCompatibleSubmitBackend(config, FakeProducer(KafkaBrokerAck()))


def test_full_kafka_backend_rejects_producer_without_send() -> None:
    config = SubmitBackendConfig(
        backend_kind="full_kafka",
        topic="candidate-events",
    )

    with pytest.raises(ValueError, match="producer.send"):
        KafkaCompatibleSubmitBackend(config, object())  # type: ignore[arg-type]


def test_full_kafka_submit_sends_stable_json_bytes_and_hides_ack_fields() -> None:
    ack = KafkaBrokerAck(
        message_id="message-7",
        partition=2,
        offset=99,
        timestamp_ms=123456,
    )
    producer = FakeProducer(ack)
    backend = KafkaCompatibleSubmitBackend(
        SubmitBackendConfig(
            backend_kind="full_kafka",
            topic="candidate-events",
        ),
        producer,
        key_field="subsystem_id",
    )

    receipt = backend.submit({"subsystem_id": "subsystem-a", "ex_type": "Ex-2"})

    assert producer.calls == [
        (
            "candidate-events",
            b'{"ex_type":"Ex-2","subsystem_id":"subsystem-a"}',
            "subsystem-a",
        )
    ]
    assert receipt == {
        "accepted": True,
        "transport_ref": _transport_ref_from_ack("candidate-events", ack),
        "warnings": (),
        "errors": (),
    }
    assert receipt["transport_ref"].startswith("kafka:")
    assert len(receipt["transport_ref"]) == len("kafka:") + 32
    assert "candidate-events" not in receipt["transport_ref"]
    assert "partition" not in receipt["transport_ref"]
    assert "offset" not in receipt["transport_ref"]
    assert "message-7" not in receipt["transport_ref"]
    assert set(receipt) == {"accepted", "transport_ref", "warnings", "errors"}
    for private_key in (
        "kafka_topic",
        "kafka_partition",
        "kafka_offset",
        "topic",
        "partition",
        "offset",
    ):
        assert private_key not in receipt


def test_full_kafka_submit_supports_mapping_ack() -> None:
    producer = FakeProducer(
        {
            "message_id": "message-8",
            "topic": "candidate-events",
            "partition": 3,
            "offset": 100,
            "timestamp_ms": 123457,
            "ignored_private_field": "not-returned",
        }
    )
    backend = KafkaCompatibleSubmitBackend(
        SubmitBackendConfig(
            backend_kind="full_kafka",
            topic="candidate-events",
        ),
        producer,
    )

    receipt = backend.submit({"ex_type": "Ex-3"})

    assert producer.calls == [("candidate-events", b'{"ex_type":"Ex-3"}', None)]
    assert receipt["accepted"] is True
    assert receipt["transport_ref"].startswith("kafka:")
    assert "ignored_private_field" not in receipt


def test_full_kafka_submit_returns_rejected_receipt_on_producer_exception() -> None:
    producer = FailingProducer()
    backend = KafkaCompatibleSubmitBackend(
        SubmitBackendConfig(
            backend_kind="full_kafka",
            topic="candidate-events",
        ),
        producer,
    )

    receipt = backend.submit({"ex_type": "Ex-1"})

    assert producer.calls == 1
    assert receipt == {
        "accepted": False,
        "transport_ref": None,
        "warnings": (),
        "errors": ("full_kafka submit failed: broker unavailable",),
    }


def test_full_kafka_raw_receipt_normalizes_to_public_submit_receipt() -> None:
    backend = KafkaCompatibleSubmitBackend(
        SubmitBackendConfig(
            backend_kind="full_kafka",
            topic="candidate-events",
        ),
        FakeProducer(KafkaBrokerAck(message_id="message-9", partition=1, offset=2)),
    )

    receipt = normalize_backend_receipt(
        backend.submit({"ex_type": "Ex-2"}),
        backend_kind="full_kafka",
        validator_version="contracts-v1",
    )

    assert receipt.backend_kind == "full_kafka"
    assert receipt.accepted is True
    assert receipt.validator_version == "contracts-v1"
    assert receipt.errors == ()
    assert set(receipt.model_dump()) == {
        "accepted",
        "receipt_id",
        "backend_kind",
        "transport_ref",
        "validator_version",
        "warnings",
        "errors",
    }


def test_full_kafka_private_leak_still_rejected_before_receipt_creation() -> None:
    with pytest.raises(ValueError, match="kafka_topic"):
        normalize_backend_receipt(
            {"accepted": True, "kafka_topic": "candidate-events"},
            backend_kind="full_kafka",
            validator_version="contracts-v1",
        )


def test_submit_receipt_dump_does_not_include_kafka_private_fields() -> None:
    receipt = SubmitReceipt(
        accepted=True,
        receipt_id="receipt-1",
        backend_kind="full_kafka",
        transport_ref="kafka:abc",
        validator_version="contracts-v1",
    )

    assert set(receipt.model_dump()) == {
        "accepted",
        "receipt_id",
        "backend_kind",
        "transport_ref",
        "validator_version",
        "warnings",
        "errors",
    }
