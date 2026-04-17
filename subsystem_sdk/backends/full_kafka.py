"""Kafka-compatible Full submit backend adapter."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from subsystem_sdk.backends.config import SubmitBackendConfig
from subsystem_sdk.submit.protocol import SubmitBackendInterface
from subsystem_sdk.submit.receipt import BackendKind


class KafkaBrokerAck(BaseModel):
    """Adapter-private broker acknowledgement details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str | None = None
    topic: str | None = None
    partition: int | None = None
    offset: int | None = None
    timestamp_ms: int | None = Field(default=None, ge=0)


class KafkaProducerProtocol(Protocol):
    """Minimal producer interface required by the Full backend adapter."""

    def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str | None = None,
    ) -> KafkaBrokerAck | Mapping[str, Any]:
        """Send serialized payload bytes to a Kafka-compatible broker."""


class KafkaCompatibleSubmitBackend(SubmitBackendInterface):
    """Full backend adapter that hides broker transport details."""

    backend_kind: BackendKind = "full_kafka"

    def __init__(
        self,
        config: SubmitBackendConfig,
        producer: KafkaProducerProtocol,
        *,
        key_field: str | None = None,
    ) -> None:
        if config.backend_kind != self.backend_kind:
            raise ValueError(
                "KafkaCompatibleSubmitBackend requires "
                "backend_kind='full_kafka'"
            )
        if config.topic is None or not config.topic.strip():
            raise ValueError("KafkaCompatibleSubmitBackend requires config.topic")
        if not callable(getattr(producer, "send", None)):
            raise ValueError(
                "KafkaCompatibleSubmitBackend requires producer.send(...)"
            )

        self._config = config
        self._producer = producer
        self._key_field = key_field

    @property
    def config(self) -> SubmitBackendConfig:
        return self._config

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        payload_bytes = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        key = self._key_from_payload(payload)

        try:
            ack = self._producer.send(self._config.topic or "", payload_bytes, key=key)
        except Exception as exc:
            return {
                "accepted": False,
                "transport_ref": None,
                "warnings": (),
                "errors": (f"full_kafka submit failed: {_error_message(exc)}",),
            }

        return {
            "accepted": True,
            "transport_ref": _transport_ref_from_ack(self._config.topic or "", ack),
            "warnings": (),
            "errors": (),
        }

    def _key_from_payload(self, payload: Mapping[str, Any]) -> str | None:
        if self._key_field is None:
            return None

        value = payload.get(self._key_field)
        if value is None:
            return None
        return str(value)


def _transport_ref_from_ack(
    topic: str, ack: KafkaBrokerAck | Mapping[str, Any]
) -> str:
    ack_data = _ack_mapping(ack)
    digest_input = {
        "topic": topic,
        "ack_topic": ack_data.get("topic"),
        "message_id": ack_data.get("message_id"),
        "partition": ack_data.get("partition"),
        "offset": ack_data.get("offset"),
        "timestamp_ms": ack_data.get("timestamp_ms"),
    }
    encoded = json.dumps(
        digest_input,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"kafka:{hashlib.sha256(encoded).hexdigest()[:32]}"


def _ack_mapping(ack: KafkaBrokerAck | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(ack, KafkaBrokerAck):
        return ack.model_dump(mode="python")
    if isinstance(ack, Mapping):
        return ack
    raise TypeError("Kafka producer ack must be KafkaBrokerAck or a mapping")


def _error_message(exc: Exception) -> str:
    message = str(exc)
    return message if message else exc.__class__.__name__
