"""Semantic guardrails that must hold before schema validation."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES

EX0_SEMANTIC: Final[str] = "metadata_or_heartbeat"
EX0_BANNED_SEMANTICS: Final[frozenset[str]] = frozenset(
    {"fact", "signal", "graph_delta", "business_event"}
)
INGEST_METADATA_FIELDS: Final[frozenset[str]] = frozenset(
    {"submitted_at", "ingest_seq", "layer_b_receipt_id"}
)
_PRODUCER_OWNED_REQUIRED: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "Ex-0": frozenset({"subsystem_id", "version", "heartbeat_at", "status"}),
        "Ex-1": frozenset({"subsystem_id", "produced_at"}),
        "Ex-2": frozenset({"subsystem_id", "produced_at"}),
        "Ex-3": frozenset({"subsystem_id", "produced_at"}),
    }
)
PRODUCER_OWNED_REQUIRED: Final[Mapping[str, frozenset[str]]] = (
    _PRODUCER_OWNED_REQUIRED
)
_EX_TYPE_FIELD: Final[str] = "ex_type"
_EX0_SEMANTIC_FIELD: Final[str] = "semantic"
_EX0_SCHEMA_MARKERS: Final[frozenset[str]] = frozenset(
    {"heartbeat_at", "last_output_at", "pending_count"}
)
_EX0_ALLOWED_PRODUCER_FIELDS: Final[frozenset[str]] = (
    _PRODUCER_OWNED_REQUIRED["Ex-0"]
    | _EX0_SCHEMA_MARKERS
    | frozenset({_EX_TYPE_FIELD, _EX0_SEMANTIC_FIELD})
)
_PRODUCED_SCHEMA_MARKERS: Final[frozenset[str]] = frozenset({"produced_at"})
_PRODUCED_EX_TYPES: Final[frozenset[str]] = frozenset({"Ex-1", "Ex-2", "Ex-3"})


class SemanticsError(ValueError):
    """Base error for producer-owned semantic guard failures."""


class Ex0SemanticError(SemanticsError):
    """Raised when Ex-0 is declared as anything except metadata or heartbeat."""


class IngestMetadataLeakError(SemanticsError):
    """Raised when producer payload includes ingest-owned metadata."""


class MissingProducerFieldError(SemanticsError):
    """Raised when a producer-owned required field is missing."""


def assert_ex0_semantic(declared_semantic: str) -> None:
    """Require Ex-0 to remain fixed as metadata or heartbeat."""

    if declared_semantic != EX0_SEMANTIC:
        raise Ex0SemanticError(
            f"Ex-0 semantic must be {EX0_SEMANTIC!r}; got {declared_semantic!r}"
        )


def assert_no_ingest_metadata(payload: Mapping[str, Any]) -> None:
    """Reject ingest metadata at the payload top level or one nested mapping level."""

    leaked_fields = set(payload).intersection(INGEST_METADATA_FIELDS)
    for value in payload.values():
        if isinstance(value, Mapping):
            leaked_fields.update(set(value).intersection(INGEST_METADATA_FIELDS))

    if leaked_fields:
        fields = ", ".join(sorted(leaked_fields))
        raise IngestMetadataLeakError(
            f"producer payload includes ingest metadata field(s): {fields}"
        )


def _coerce_payload_mapping(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload

    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped

    raise TypeError("producer payload must be a mapping or expose model_dump()")


def _extract_payload_ex_type(payload: Mapping[str, Any]) -> str | None:
    value = payload.get(_EX_TYPE_FIELD)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SemanticsError("producer payload ex_type must be a string")
    if value not in SUPPORTED_EX_TYPES:
        raise SemanticsError(f"unsupported Ex type: {value!r}")
    return value


def _infer_ex0_payload(payload: Mapping[str, Any]) -> bool:
    return bool(set(payload).intersection(_EX0_SCHEMA_MARKERS))


def _assert_payload_schema_matches(ex_type: str, payload: Mapping[str, Any]) -> None:
    has_ex0_shape = _infer_ex0_payload(payload)
    has_produced_shape = bool(set(payload).intersection(_PRODUCED_SCHEMA_MARKERS))

    if has_ex0_shape and has_produced_shape:
        raise SemanticsError(
            "payload mixes Ex-0 heartbeat fields with produced payload fields"
        )
    if has_ex0_shape and ex_type != "Ex-0":
        raise SemanticsError(
            f"payload schema looks like 'Ex-0' but declared ex_type is {ex_type!r}"
        )
    if has_produced_shape and ex_type not in _PRODUCED_EX_TYPES:
        raise SemanticsError(
            f"payload schema looks like 'Ex-1/2/3' but declared ex_type is {ex_type!r}"
        )


def _derive_ex_type(payload: Mapping[str, Any]) -> str:
    ex_type = _extract_payload_ex_type(payload)
    if ex_type is None and _infer_ex0_payload(payload):
        ex_type = "Ex-0"
    if ex_type is None:
        raise SemanticsError("producer payload must declare ex_type")

    _assert_payload_schema_matches(ex_type, payload)
    return ex_type


def _assert_ex0_payload_semantic(payload: Mapping[str, Any]) -> None:
    disallowed_fields = set(payload).difference(_EX0_ALLOWED_PRODUCER_FIELDS)
    if disallowed_fields:
        fields = ", ".join(sorted(disallowed_fields))
        raise Ex0SemanticError(
            f"Ex-0 producer payload includes non-heartbeat field(s): {fields}"
        )

    declared_semantic = payload.get(_EX0_SEMANTIC_FIELD, EX0_SEMANTIC)
    if not isinstance(declared_semantic, str):
        raise Ex0SemanticError(
            f"Ex-0 semantic must be {EX0_SEMANTIC!r}; got {declared_semantic!r}"
        )

    assert_ex0_semantic(declared_semantic)


def assert_producer_only(payload: Any, ex_type: str | None = None) -> None:
    """Require a supported Ex payload to contain only producer-owned fields."""

    explicit_ex_type = ex_type
    if isinstance(payload, str):
        explicit_ex_type = payload
        payload = ex_type

    payload_mapping = _coerce_payload_mapping(payload)
    payload_ex_type = _derive_ex_type(payload_mapping)
    if explicit_ex_type is not None:
        if explicit_ex_type not in SUPPORTED_EX_TYPES:
            raise SemanticsError(f"unsupported Ex type: {explicit_ex_type!r}")
        if explicit_ex_type != payload_ex_type:
            raise SemanticsError(
                "declared Ex type "
                f"{explicit_ex_type!r} does not match payload ex_type {payload_ex_type!r}"
            )

    if payload_ex_type == "Ex-0":
        _assert_ex0_payload_semantic(payload_mapping)

    assert_no_ingest_metadata(payload_mapping)

    required_fields = _PRODUCER_OWNED_REQUIRED[payload_ex_type]
    missing_fields = required_fields.difference(payload_mapping)
    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise MissingProducerFieldError(
            f"{payload_ex_type} producer payload missing required field(s): {fields}"
        )
