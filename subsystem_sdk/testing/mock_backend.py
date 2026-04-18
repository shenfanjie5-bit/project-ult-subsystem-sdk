"""Testing backend that records submit and heartbeat traffic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from subsystem_sdk._json import freeze_json_like
from subsystem_sdk.backends import MockSubmitBackend


@dataclass(frozen=True)
class BackendEvent:
    """One backend event captured by ``MockBackend``."""

    kind: Literal["submit", "heartbeat"]
    payload: Mapping[str, Any]


class MockBackend(MockSubmitBackend):
    """Single mock backend usable by submit and heartbeat clients."""

    def __init__(
        self,
        *,
        accepted: bool = True,
        transport_ref: str | None = None,
        receipt_id: str | None = None,
        warnings: Sequence[str] = (),
        errors: Sequence[str] = (),
    ) -> None:
        super().__init__(
            accepted=accepted,
            transport_ref=transport_ref,
            receipt_id=receipt_id,
            warnings=warnings,
            errors=errors,
        )
        self._events: list[BackendEvent] = []
        self._heartbeat_payloads: list[dict[str, Any]] = []

    @property
    def events(self) -> tuple[BackendEvent, ...]:
        return tuple(self._events)

    @property
    def heartbeat_payloads(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(self._heartbeat_payloads))

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._events.append(
            BackendEvent(kind="submit", payload=freeze_json_like(dict(payload)))
        )
        return super().submit(payload)

    def send(self, ex0_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        copied_payload = deepcopy(dict(ex0_payload))
        self._heartbeat_payloads.append(copied_payload)
        self._events.append(
            BackendEvent(kind="heartbeat", payload=freeze_json_like(copied_payload))
        )
        receipt: dict[str, Any] = {
            "accepted": self._accepted,
            "transport_ref": self._transport_ref
            if self._transport_ref is not None
            else f"mock-heartbeat-{len(self._heartbeat_payloads)}",
            "warnings": self._warnings,
            "errors": self._errors,
        }
        if self._receipt_id is not None:
            receipt["receipt_id"] = self._receipt_id
        return receipt
