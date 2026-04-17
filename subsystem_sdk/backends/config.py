"""Submit backend adapter configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from subsystem_sdk.submit.receipt import BackendKind


class SubmitBackendConfig(BaseModel):
    """Configuration consumed by backend adapters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_kind: BackendKind
    dsn: str | None = None
    queue_table: str | None = None
    connect_timeout_ms: int = Field(default=500, ge=1)
