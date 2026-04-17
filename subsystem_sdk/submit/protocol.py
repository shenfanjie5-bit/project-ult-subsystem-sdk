"""Backend protocol for submit adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from subsystem_sdk.submit.receipt import BackendKind, SubmitReceipt


class SubmitBackendInterface(Protocol):
    """Adapter boundary consumed by the unified submit client."""

    backend_kind: BackendKind

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | SubmitReceipt:
        """Submit a producer payload and return an adapter receipt."""
