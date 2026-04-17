"""Factory for submit backend adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, assert_never

from subsystem_sdk.backends.config import SubmitBackendConfig
from subsystem_sdk.backends.full_kafka import (
    KafkaCompatibleSubmitBackend,
    KafkaProducerProtocol,
)
from subsystem_sdk.backends.lite_pg import PgSubmitBackend
from subsystem_sdk.backends.mock import MockSubmitBackend
from subsystem_sdk.submit.protocol import SubmitBackendInterface


def build_submit_backend(
    config: SubmitBackendConfig,
    *,
    pg_connection_factory: Callable[[SubmitBackendConfig], Any] | None = None,
    kafka_producer: KafkaProducerProtocol | None = None,
    mock_backend: MockSubmitBackend | None = None,
) -> SubmitBackendInterface:
    """Build the configured submit backend without exposing transport details."""

    if config.backend_kind == "lite_pg":
        if config.dsn is None and pg_connection_factory is None:
            raise ValueError(
                "lite_pg backend requires pg_connection_factory or config.dsn"
            )
        return PgSubmitBackend(config, connection_factory=pg_connection_factory)

    if config.backend_kind == "full_kafka":
        if kafka_producer is None:
            raise ValueError("full_kafka backend requires kafka_producer")
        return KafkaCompatibleSubmitBackend(config, kafka_producer)

    if config.backend_kind == "mock":
        return mock_backend or MockSubmitBackend()

    assert_never(config.backend_kind)
