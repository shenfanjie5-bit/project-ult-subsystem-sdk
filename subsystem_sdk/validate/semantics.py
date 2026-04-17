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


def assert_producer_only(ex_type: str, payload: Mapping[str, Any]) -> None:
    """Require a supported Ex payload to contain only producer-owned fields."""

    if ex_type not in SUPPORTED_EX_TYPES:
        raise SemanticsError(f"unsupported Ex type: {ex_type!r}")

    assert_no_ingest_metadata(payload)

    required_fields = _PRODUCER_OWNED_REQUIRED[ex_type]
    missing_fields = required_fields.difference(payload)
    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise MissingProducerFieldError(
            f"{ex_type} producer payload missing required field(s): {fields}"
        )
