"""Submit backend adapter configuration."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from subsystem_sdk.submit.receipt import BackendKind


class SubmitBackendConfig(BaseModel):
    """Configuration consumed by backend adapters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_kind: BackendKind
    dsn: str | None = None
    queue_table: str | None = None
    connect_timeout_ms: int = Field(default=500, ge=1)
    topic: str | None = None
    client_id: str | None = None
    delivery_timeout_ms: int = Field(default=1000, ge=1)

    @model_validator(mode="after")
    def _validate_full_kafka_topic(self) -> Self:
        if self.backend_kind == "full_kafka" and (
            self.topic is None or not self.topic.strip()
        ):
            raise ValueError(
                "SubmitBackendConfig.topic is required when "
                "backend_kind='full_kafka'"
            )
        return self
