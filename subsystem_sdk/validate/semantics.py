"""Producer payload semantic guards."""

from typing import Any, Final, Mapping

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES

EX0_SEMANTIC: Final[str] = "metadata_or_heartbeat"
EX0_BANNED_SEMANTICS: Final[frozenset[str]] = frozenset(
    {"fact", "signal", "graph_delta", "business_event"}
)
INGEST_METADATA_FIELDS: Final[frozenset[str]] = frozenset(
    {"submitted_at", "ingest_seq", "layer_b_receipt_id"}
)
PRODUCER_OWNED_REQUIRED: Final[dict[str, frozenset[str]]] = {
    "Ex-0": frozenset({"subsystem_id", "version", "heartbeat_at", "status"}),
    "Ex-1": frozenset({"subsystem_id", "produced_at"}),
    "Ex-2": frozenset({"subsystem_id", "produced_at"}),
    "Ex-3": frozenset({"subsystem_id", "produced_at"}),
}


class SemanticsError(ValueError):
    """Base error for producer payload semantic violations."""


class Ex0SemanticError(SemanticsError):
    """Raised when Ex-0 is declared with a non-heartbeat semantic."""


class IngestMetadataLeakError(SemanticsError):
    """Raised when backend-owned ingest metadata appears in producer payload."""


class MissingProducerFieldError(SemanticsError):
    """Raised when a producer-owned required field is absent."""


def assert_ex0_semantic(declared_semantic: str) -> None:
    """Require Ex-0 to remain metadata / heartbeat only."""

    if declared_semantic != EX0_SEMANTIC:
        raise Ex0SemanticError(
            f"Ex-0 semantic must be {EX0_SEMANTIC!r}; got {declared_semantic!r}"
        )


def assert_no_ingest_metadata(payload: Mapping[str, Any]) -> None:
    """Reject ingest metadata at the top level or one nested mapping level."""

    for field in sorted(INGEST_METADATA_FIELDS):
        if field in payload:
            raise IngestMetadataLeakError(
                f"Ingest metadata field {field!r} is not allowed in producer payload"
            )

    for value in payload.values():
        if not isinstance(value, Mapping):
            continue
        for field in sorted(INGEST_METADATA_FIELDS):
            if field in value:
                raise IngestMetadataLeakError(
                    f"Ingest metadata field {field!r} is not allowed in producer payload"
                )


def assert_producer_only(ex_type: str, payload: Mapping[str, Any]) -> None:
    """Require producer payloads to contain only producer-owned contract fields."""

    if ex_type not in SUPPORTED_EX_TYPES:
        raise SemanticsError(
            f"Unsupported ex_type {ex_type!r}; expected one of {SUPPORTED_EX_TYPES!r}"
        )

    assert_no_ingest_metadata(payload)

    missing_fields = PRODUCER_OWNED_REQUIRED[ex_type].difference(payload)
    if missing_fields:
        formatted = ", ".join(sorted(missing_fields))
        raise MissingProducerFieldError(
            f"{ex_type} producer payload is missing required field(s): {formatted}"
        )
