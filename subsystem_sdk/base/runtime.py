"""Scoped SDK runtime used by public package entrypoints."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol

from subsystem_sdk.heartbeat.payload import HeartbeatStatus
from subsystem_sdk.submit.receipt import SubmitReceipt


class RuntimeNotConfiguredError(RuntimeError):
    """Raised when public SDK entrypoints are used before runtime wiring."""


class RuntimeAlreadyConfiguredError(RuntimeError):
    """Raised when a scoped runtime binding would replace another runtime."""


class SDKRuntime(Protocol):
    """Runtime surface consumed by public submit and heartbeat functions."""

    def submit(self, payload: Mapping[str, Any]) -> SubmitReceipt:
        """Submit a producer payload."""

    def send_heartbeat(
        self,
        status_payload: HeartbeatStatus | Mapping[str, Any],
    ) -> SubmitReceipt:
        """Send an Ex-0 heartbeat status payload."""


_SCOPED_RUNTIME: ContextVar[SDKRuntime | None] = ContextVar(
    "subsystem_sdk_runtime",
    default=None,
)


@contextmanager
def configure_runtime(runtime: SDKRuntime) -> Iterator[SDKRuntime]:
    """Bind public SDK entrypoints to a runtime for the current execution scope."""

    active_runtime = _SCOPED_RUNTIME.get()
    if active_runtime is not None and active_runtime is not runtime:
        raise RuntimeAlreadyConfiguredError(
            "subsystem_sdk runtime is already configured for this execution "
            "scope; exit the active configure_runtime(...) scope before "
            "binding a different runtime"
        )

    token = _SCOPED_RUNTIME.set(runtime)
    try:
        yield runtime
    finally:
        _SCOPED_RUNTIME.reset(token)


def get_runtime() -> SDKRuntime:
    """Return the configured runtime or fail with a clear setup error."""

    runtime = _SCOPED_RUNTIME.get()
    if runtime is None:
        raise RuntimeNotConfiguredError(
            "subsystem_sdk runtime is not configured; create a "
            "BaseSubsystemContext and use configure_runtime(context) as a "
            "scoped context manager before using submit() or send_heartbeat()"
        )
    return runtime


def _clear_runtime_for_tests() -> None:
    _SCOPED_RUNTIME.set(None)


__all__ = [
    "RuntimeAlreadyConfiguredError",
    "RuntimeNotConfiguredError",
    "SDKRuntime",
    "configure_runtime",
    "get_runtime",
]
