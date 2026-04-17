from __future__ import annotations

import json
from typing import Any

import pytest

from subsystem_sdk.backends import (
    KafkaBrokerAck,
    KafkaCompatibleSubmitBackend,
    MockSubmitBackend,
    PgSubmitBackend,
    SubmitBackendConfig,
    build_submit_backend,
)


class FakePgCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.row = (101,)

    def execute(self, sql: str, params: tuple[str]) -> None:
        self.executed_sql.append(sql)
        json.loads(params[0])

    def fetchone(self) -> tuple[int]:
        return self.row

    def close(self) -> None:
        return None


class FakePgConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakePgCursor()
        self.commits = 0
        self.closed = False

    def cursor(self) -> FakePgCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


class FakeKafkaProducer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str | None]] = []

    def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str | None = None,
    ) -> KafkaBrokerAck:
        self.calls.append((topic, payload, key))
        return KafkaBrokerAck(message_id="message-1", partition=1, offset=5)


def test_build_submit_backend_returns_pg_backend_with_injected_connection() -> None:
    config = SubmitBackendConfig(backend_kind="lite_pg", queue_table="submit_queue")
    connection = FakePgConnection()
    calls: list[SubmitBackendConfig] = []

    def connection_factory(received: SubmitBackendConfig) -> FakePgConnection:
        calls.append(received)
        return connection

    backend = build_submit_backend(config, pg_connection_factory=connection_factory)
    receipt = backend.submit({"ex_type": "Ex-2", "subsystem_id": "subsystem-a"})

    assert isinstance(backend, PgSubmitBackend)
    assert backend.backend_kind == "lite_pg"
    assert calls == [config]
    assert receipt["accepted"] is True
    assert receipt["transport_ref"] == "101"
    assert connection.commits == 1
    assert connection.closed is True


def test_build_submit_backend_lite_requires_dsn_or_connection_factory() -> None:
    config = SubmitBackendConfig(backend_kind="lite_pg")

    with pytest.raises(ValueError, match="lite_pg backend requires"):
        build_submit_backend(config)


def test_build_submit_backend_lite_with_dsn_does_not_require_kafka() -> None:
    config = SubmitBackendConfig(
        backend_kind="lite_pg",
        dsn="postgresql://example/subsystem",
    )

    backend = build_submit_backend(config)

    assert isinstance(backend, PgSubmitBackend)
    assert backend.backend_kind == "lite_pg"


def test_build_submit_backend_returns_full_kafka_backend() -> None:
    producer = FakeKafkaProducer()
    config = SubmitBackendConfig(
        backend_kind="full_kafka",
        topic="candidate-events",
    )

    backend = build_submit_backend(config, kafka_producer=producer)
    receipt = backend.submit({"ex_type": "Ex-2", "subsystem_id": "subsystem-a"})

    assert isinstance(backend, KafkaCompatibleSubmitBackend)
    assert backend.backend_kind == "full_kafka"
    assert producer.calls == [
        (
            "candidate-events",
            b'{"ex_type":"Ex-2","subsystem_id":"subsystem-a"}',
            None,
        )
    ]
    assert receipt["accepted"] is True
    assert str(receipt["transport_ref"]).startswith("kafka:")


def test_build_submit_backend_full_requires_kafka_producer() -> None:
    config = SubmitBackendConfig(
        backend_kind="full_kafka",
        topic="candidate-events",
    )

    with pytest.raises(ValueError, match="full_kafka backend requires kafka_producer"):
        build_submit_backend(config)


def test_build_submit_backend_returns_mock_backend() -> None:
    config = SubmitBackendConfig(backend_kind="mock")

    backend = build_submit_backend(config)
    receipt = backend.submit({"ex_type": "Ex-2"})

    assert isinstance(backend, MockSubmitBackend)
    assert backend.backend_kind == "mock"
    assert receipt["accepted"] is True
    assert receipt["transport_ref"] == "mock-1"


def test_build_submit_backend_uses_injected_mock_backend() -> None:
    injected = MockSubmitBackend(receipt_id="receipt-1")

    backend = build_submit_backend(
        SubmitBackendConfig(backend_kind="mock"),
        mock_backend=injected,
    )

    assert backend is injected
    assert backend.submit({"ex_type": "Ex-1"})["receipt_id"] == "receipt-1"
