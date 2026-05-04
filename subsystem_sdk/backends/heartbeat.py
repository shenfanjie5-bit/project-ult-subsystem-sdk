"""Heartbeat backend adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from subsystem_sdk.submit.protocol import SubmitBackendInterface
from subsystem_sdk.submit.receipt import BackendKind, SubmitReceipt
from subsystem_sdk.validate.result import ValidationResult


class SubmitBackendHeartbeatAdapter:
    """Adapt a submit backend for Ex-0 heartbeat dispatch."""

    def __init__(self, submit_backend: SubmitBackendInterface) -> None:
        self._submit_backend = submit_backend

    @property
    def backend_kind(self) -> BackendKind:
        return self._submit_backend.backend_kind

    def send(self, ex0_payload: Mapping[str, Any]) -> Mapping[str, Any] | SubmitReceipt:
        return self._submit_backend.submit(ex0_payload)

    def prepare_dispatch_payload(
        self,
        wire_payload: Mapping[str, Any],
        validation: ValidationResult,
    ) -> Mapping[str, Any]:
        preparer = getattr(self._submit_backend, "prepare_dispatch_payload", None)
        if preparer is None:
            return wire_payload
        return preparer(wire_payload, validation)
