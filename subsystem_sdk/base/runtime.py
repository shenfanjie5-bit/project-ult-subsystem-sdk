"""Configured SDK runtime used by public package entrypoints."""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from typing import Any, Protocol

from subsystem_sdk.heartbeat.payload import HeartbeatStatus
from subsystem_sdk.submit.receipt import SubmitReceipt


class RuntimeNotConfiguredError(RuntimeError):
    """Raised when public SDK entrypoints are used before runtime wiring."""


class SDKRuntime(Protocol):
    """Runtime surface consumed by public submit and heartbeat functions."""

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        """Submit a producer payload."""

    def send_heartbeat(
        self,
        status_payload: HeartbeatStatus | Mapping[str, Any],
    ) -> SubmitReceipt:
        """Send an Ex-0 heartbeat status payload."""


_RUNTIME_LOCK = RLock()
_configured_runtime: SDKRuntime | None = None


def configure_runtime(runtime: SDKRuntime) -> None:
    """Configure the process-local runtime used by public SDK entrypoints."""

    global _configured_runtime
    with _RUNTIME_LOCK:
        _configured_runtime = runtime


def get_runtime() -> SDKRuntime:
    """Return the configured runtime or fail with a clear setup error."""

    with _RUNTIME_LOCK:
        runtime = _configured_runtime

    if runtime is None:
        raise RuntimeNotConfiguredError(
            "subsystem_sdk runtime is not configured; create a "
            "BaseSubsystemContext and call configure_runtime(context) before "
            "using submit() or send_heartbeat()"
        )
    return runtime


def _clear_runtime_for_tests() -> None:
    global _configured_runtime
    with _RUNTIME_LOCK:
        _configured_runtime = None


__all__ = [
    "RuntimeNotConfiguredError",
    "SDKRuntime",
    "configure_runtime",
    "get_runtime",
]
