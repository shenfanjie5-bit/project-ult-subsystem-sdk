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
    def _validate_backend_fields(self) -> Self:
        if self.dsn is not None and not self.dsn.strip():
            raise ValueError("SubmitBackendConfig.dsn cannot be blank")
        if self.queue_table is not None and not self.queue_table.strip():
            raise ValueError("SubmitBackendConfig.queue_table cannot be blank")
        if self.client_id is not None and not self.client_id.strip():
            raise ValueError("SubmitBackendConfig.client_id cannot be blank")

        if self.backend_kind == "full_kafka" and not _has_text(self.topic):
            raise ValueError(
                "SubmitBackendConfig.topic is required when "
                "backend_kind='full_kafka'"
            )
        return self


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())
