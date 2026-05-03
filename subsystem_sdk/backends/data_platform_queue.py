"""data-platform candidate queue submit backend adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from subsystem_sdk.submit.receipt import BackendKind
from subsystem_sdk.validate.result import ValidationResult

SubmitCandidateFunc = Callable[[Mapping[str, Any]], Any]

_BACKEND_KIND: BackendKind = "data_platform_queue"
_SUBSYSTEM_ID_FIELD = "subsystem_id"
_QUEUE_ENVELOPE_FIELDS = frozenset({"payload_type", "submitted_by"})
_INGEST_METADATA_FIELDS = frozenset(
    {"submitted_at", "ingest_seq", "layer_b_receipt_id"}
)
_SDK_ENVELOPE_FIELDS = frozenset({"ex_type", "semantic", "produced_at"})
_FORBIDDEN_WIRE_FIELDS = (
    _QUEUE_ENVELOPE_FIELDS | _INGEST_METADATA_FIELDS | _SDK_ENVELOPE_FIELDS
)


class DataPlatformQueueSubmitBackend:
    """Bridge SDK-validated Ex payloads into data-platform's candidate_queue."""

    backend_kind: BackendKind = _BACKEND_KIND

    def __init__(
        self,
        submit_candidate_func: SubmitCandidateFunc | None = None,
    ) -> None:
        self._submit_candidate_func = submit_candidate_func

    def prepare_dispatch_payload(
        self,
        wire_payload: Mapping[str, Any],
        validation: ValidationResult,
    ) -> Mapping[str, Any]:
        forbidden = sorted(_FORBIDDEN_WIRE_FIELDS.intersection(wire_payload))
        if forbidden:
            raise ValueError(
                "data_platform_queue wire payload includes reserved field(s): "
                f"{forbidden}"
            )

        subsystem_id = wire_payload.get(_SUBSYSTEM_ID_FIELD)
        if not isinstance(subsystem_id, str) or not subsystem_id.strip():
            raise ValueError(
                "data_platform_queue requires non-empty subsystem_id to derive "
                "submitted_by"
            )

        envelope = {
            "payload_type": validation.ex_type,
            "submitted_by": subsystem_id.strip(),
        }
        envelope.update(dict(wire_payload))
        return envelope

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            item = self._resolve_submit_candidate()(payload)
            transport_ref = str(_candidate_id(item))
        except Exception:  # noqa: BLE001 - backend failures become receipts.
            return {
                "accepted": False,
                "transport_ref": None,
                "warnings": (),
                "errors": ("data_platform_queue submit failed",),
            }

        return {
            "accepted": True,
            "transport_ref": transport_ref,
            "warnings": (),
            "errors": (),
        }

    def _resolve_submit_candidate(self) -> SubmitCandidateFunc:
        if self._submit_candidate_func is not None:
            return self._submit_candidate_func

        try:
            from data_platform.queue.api import submit_candidate
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "data_platform_queue backend requires project-ult-data-platform "
                "on PYTHONPATH or an injected submit_candidate_func"
            ) from exc

        return submit_candidate

def _candidate_id(item: Any) -> Any:
    if isinstance(item, Mapping) and "id" in item:
        return item["id"]
    return getattr(item, "id")


__all__ = [
    "DataPlatformQueueSubmitBackend",
    "SubmitCandidateFunc",
]
