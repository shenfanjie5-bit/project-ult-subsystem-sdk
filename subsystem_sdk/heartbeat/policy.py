"""Heartbeat policy primitives."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeartbeatPolicy:
    """Caller-managed heartbeat timing policy."""

    interval_seconds: int = 30
    timeout_ms: int = 300

    def __post_init__(self) -> None:
        for field_name, value in (
            ("interval_seconds", self.interval_seconds),
            ("timeout_ms", self.timeout_ms),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be an integer")
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")


DEFAULT_HEARTBEAT_POLICY = HeartbeatPolicy()
