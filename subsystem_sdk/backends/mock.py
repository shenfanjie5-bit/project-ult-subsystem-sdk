"""In-memory submit backend for tests and local wiring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from subsystem_sdk.submit.receipt import BackendKind


class MockSubmitBackend:
    """Submit backend that records payload copies and returns raw receipts."""

    backend_kind: BackendKind = "mock"

    def __init__(
        self,
        *,
        accepted: bool = True,
        transport_ref: str | None = None,
        receipt_id: str | None = None,
        warnings: Sequence[str] = (),
        errors: Sequence[str] = (),
    ) -> None:
        self._accepted = accepted
        self._transport_ref = transport_ref
        self._receipt_id = receipt_id
        self._warnings = tuple(warnings)
        self._errors = tuple(errors)
        self._submitted_payloads: list[dict[str, Any]] = []

    @property
    def submitted_payloads(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(self._submitted_payloads))

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._submitted_payloads.append(deepcopy(dict(payload)))
        receipt: dict[str, Any] = {
            "accepted": self._accepted,
            "transport_ref": self._transport_ref
            if self._transport_ref is not None
            else f"mock-{len(self._submitted_payloads)}",
            "warnings": self._warnings,
            "errors": self._errors,
        }
        if self._receipt_id is not None:
            receipt["receipt_id"] = self._receipt_id
        return receipt
