"""Backend protocol for heartbeat adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from subsystem_sdk.submit.receipt import BackendKind, SubmitReceipt


class HeartbeatBackendInterface(Protocol):
    """Adapter boundary consumed by the heartbeat client."""

    backend_kind: BackendKind

    def send(self, ex0_payload: Mapping[str, Any]) -> Mapping[str, Any] | SubmitReceipt:
        """Send an Ex-0 heartbeat payload and return an adapter receipt."""
