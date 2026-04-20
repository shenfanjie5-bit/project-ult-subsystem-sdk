"""Main Ex payload validation dispatcher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

from pydantic import BaseModel, ValidationError

from subsystem_sdk._contracts import (
    SUPPORTED_EX_TYPES,
    ContractsSchemaError,
    ContractsUnavailableError,
    UnknownExTypeError,
    get_ex_schema,
    get_schema_version,
)
from . import registry as hook_registry
from . import semantics
from .preflight import (
    EntityPreflightResult,
    EntityRegistryLookup,
    PreflightPolicy,
    run_entity_preflight,
    should_run_entity_preflight,
)
from .result import ExType, ValidationResult

_FALLBACK_EX_TYPE: Final[ExType] = "Ex-0"
_UNKNOWN_SCHEMA_VERSION: Final[str] = "unknown"
_UNKNOWN_SCHEMA_VERSION_WARNING: Final[str] = (
    "contracts schema version is unavailable; using 'unknown'"
)
# SDK-internal "envelope" fields used for routing/derivation inside the SDK
# but NOT part of the Layer B wire payload schema in ``contracts``. The
# contracts Ex payload models declare ``extra='forbid'`` — sending these
# fields through ``schema.model_validate`` would falsely fail validation.
# Strip them right before model_validate; producer-owned semantic guards
# already ran above and have already assert_no_ingest_metadata-checked
# the full payload mapping (including the envelope), so dropping them
# here only narrows what contracts sees.
#
# Members:
# - ex_type / semantic: SDK routing wrapper around Ex-0 payloads.
# - produced_at: SDK guard marker the SDK uses to recognize Ex-1/2/3
#   shape (PRODUCER_OWNED_REQUIRED["Ex-1"]={"subsystem_id","produced_at"}
#   etc.). contracts.schemas Ex1CandidateFact/Ex2CandidateSignal/
#   Ex3CandidateGraphDelta currently don't define a produced_at field —
#   if/when contracts adds it to BaseExPayload, drop it from this strip
#   set so the value reaches Layer B unchanged. (codex stage-2.7 P1
#   follow-up: makes Ex-1/2/3 round-trip with real contracts work.)
_SDK_ENVELOPE_FIELDS: Final[frozenset[str]] = frozenset(
    {"ex_type", "semantic", "produced_at"}
)


def _strip_sdk_envelope(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a payload mapping with SDK envelope fields removed.

    Pre-condition: ``semantics.assert_producer_only`` has already validated
    the full ``payload`` (including ex_type/semantic). What we hand to
    contracts is the WIRE shape (producer-owned fields only), since the
    contracts Ex payload schemas don't model SDK routing fields.
    """

    if not _SDK_ENVELOPE_FIELDS.intersection(payload):
        return payload
    return {k: v for k, v in payload.items() if k not in _SDK_ENVELOPE_FIELDS}
def _coerce_ex_type(ex_type: str) -> ExType:
    if ex_type not in SUPPORTED_EX_TYPES:
        raise UnknownExTypeError(f"unsupported Ex type: {ex_type!r}")
    return cast(ExType, ex_type)


def _as_mapping(payload: Mapping[str, Any] | BaseModel) -> Mapping[str, Any]:
    if isinstance(payload, BaseModel):
        dumped = payload.model_dump(mode="python")
        if isinstance(dumped, Mapping):
            return dumped
    elif isinstance(payload, Mapping):
        return payload

    raise TypeError("payload must be a mapping or Pydantic BaseModel")


def _read_model_metadata_ex_type(model_type: type) -> str | None:
    for attr_name in ("ex_type", "EX_TYPE"):
        value = getattr(model_type, attr_name, None)
        if isinstance(value, str):
            return value

    model_config = getattr(model_type, "model_config", None)
    if isinstance(model_config, Mapping):
        value = model_config.get("ex_type")
        if isinstance(value, str):
            return value

    model_fields = getattr(model_type, "model_fields", None)
    if isinstance(model_fields, Mapping):
        field = model_fields.get("ex_type")
        default = getattr(field, "default", None)
        if isinstance(default, str):
            return default

    return None


def _extract_payload_ex_type(payload: Mapping[str, Any]) -> str | None:
    ex_type = payload.get("ex_type")
    if ex_type is None:
        return None
    if not isinstance(ex_type, str):
        raise semantics.SemanticsError("producer payload ex_type must be a string")
    return ex_type


def _identify_ex_type(payload: Mapping[str, Any] | BaseModel) -> str:
    payload_mapping = _as_mapping(payload)
    payload_ex_type = _extract_payload_ex_type(payload_mapping)
    model_ex_type = (
        _read_model_metadata_ex_type(type(payload))
        if isinstance(payload, BaseModel)
        else None
    )

    if payload_ex_type is not None and model_ex_type is not None:
        if payload_ex_type != model_ex_type:
            raise semantics.SemanticsError(
                "payload ex_type "
                f"{payload_ex_type!r} does not match model metadata {model_ex_type!r}"
            )

    ex_type = payload_ex_type or model_ex_type
    if ex_type is None:
        raise semantics.SemanticsError("producer payload must declare ex_type")

    _coerce_ex_type(ex_type)
    return ex_type


def _failure_ex_type(payload: Any) -> ExType:
    try:
        payload_mapping = _as_mapping(payload)
    except TypeError:
        return _FALLBACK_EX_TYPE

    ex_type = payload_mapping.get("ex_type")
    if isinstance(ex_type, str) and ex_type in SUPPORTED_EX_TYPES:
        return cast(ExType, ex_type)
    return _FALLBACK_EX_TYPE


def _schema_version_warnings(schema_version: str) -> tuple[str, ...]:
    if schema_version == _UNKNOWN_SCHEMA_VERSION:
        return (_UNKNOWN_SCHEMA_VERSION_WARNING,)
    return ()


def _format_pydantic_errors(error: ValidationError) -> tuple[str, ...]:
    formatted: list[str] = []
    for item in error.errors():
        loc_parts = item.get("loc", ())
        loc = ".".join(str(part) for part in loc_parts) if loc_parts else "payload"
        message = item.get("msg", "validation error")
        formatted.append(f"{loc}: {message}")
    return tuple(formatted) or (str(error),)


def _fail(
    ex_type: ExType,
    *,
    field_errors: Sequence[str],
    schema_version: str = _UNKNOWN_SCHEMA_VERSION,
    warnings: Sequence[str] = (),
) -> ValidationResult:
    return ValidationResult.fail(
        ex_type=ex_type,
        schema_version=schema_version,
        field_errors=field_errors,
        warnings=warnings,
    )


def _preflight_block_errors(preflight: EntityPreflightResult) -> tuple[str, ...]:
    refs_text = ", ".join(preflight.unresolved_refs)
    return (f"entity preflight blocked unresolved reference(s): {refs_text}",)


def _should_run_preflight(
    result: ValidationResult, preflight_policy: PreflightPolicy
) -> bool:
    return should_run_entity_preflight(
        is_valid=result.is_valid,
        ex_type=result.ex_type,
        policy=preflight_policy,
    )


def _apply_preflight(
    result: ValidationResult,
    preflight: EntityPreflightResult,
) -> ValidationResult:
    """Merge entity preflight diagnostics into a validation result."""

    preflight_payload = preflight.to_validation_preflight()
    warnings = result.warnings + preflight.warnings

    if preflight.should_block:
        return ValidationResult.fail(
            ex_type=result.ex_type,
            schema_version=result.schema_version,
            field_errors=_preflight_block_errors(preflight),
            warnings=warnings,
            preflight=preflight_payload,
        )

    if result.is_valid:
        return ValidationResult.ok(
            ex_type=result.ex_type,
            schema_version=result.schema_version,
            warnings=warnings,
            preflight=preflight_payload,
        )

    return ValidationResult.fail(
        ex_type=result.ex_type,
        schema_version=result.schema_version,
        field_errors=result.field_errors,
        warnings=warnings,
        preflight=preflight_payload,
    )


def _assert_schema_metadata_matches(schema: type, ex_type: str) -> None:
    schema_ex_type = _read_model_metadata_ex_type(schema)
    if schema_ex_type is not None and schema_ex_type != ex_type:
        raise semantics.SemanticsError(
            "payload ex_type "
            f"{ex_type!r} does not match contracts schema metadata {schema_ex_type!r}"
        )


def validate_payload(
    payload: Mapping[str, Any] | BaseModel,
    *,
    entity_lookup: EntityRegistryLookup | None = None,
    preflight_policy: PreflightPolicy = "skip",
) -> ValidationResult:
    """Validate an Ex payload against contracts and producer-side guardrails."""

    try:
        payload_mapping = _as_mapping(payload)
    except TypeError as exc:
        return _fail(_FALLBACK_EX_TYPE, field_errors=(str(exc),))

    try:
        semantics.assert_producer_only(payload_mapping)
        ex_type = _coerce_ex_type(_identify_ex_type(payload))
    except (semantics.SemanticsError, UnknownExTypeError) as exc:
        return _fail(_failure_ex_type(payload_mapping), field_errors=(str(exc),))

    try:
        schema = get_ex_schema(ex_type)
    except (ContractsUnavailableError, UnknownExTypeError, ContractsSchemaError) as exc:
        return _fail(ex_type, field_errors=(str(exc),))

    schema_version = get_schema_version(schema)
    warnings = _schema_version_warnings(schema_version)

    try:
        _assert_schema_metadata_matches(schema, ex_type)
        # CLAUDE.md: contracts is the SINGLE SCHEMA SOURCE OF TRUTH.
        # SDK envelope fields (ex_type, semantic) are routing-only — strip
        # them here so the contracts model_validate sees the WIRE shape it
        # actually defines (producer-owned fields only). Without this,
        # contracts.schemas.Ex0Metadata's extra='forbid' rejects the SDK's
        # whole envelope and validate_payload returns invalid even though
        # the producer fields are well-formed.
        wire_payload = _strip_sdk_envelope(payload_mapping)
        schema.model_validate(wire_payload)
    except semantics.SemanticsError as exc:
        return _fail(
            ex_type,
            schema_version=schema_version,
            field_errors=(str(exc),),
            warnings=warnings,
        )
    except ValidationError as exc:
        return _fail(
            ex_type,
            schema_version=schema_version,
            field_errors=_format_pydantic_errors(exc),
            warnings=warnings,
        )

    hook_warnings = hook_registry.run_hooks(ex_type, payload_mapping)
    result = ValidationResult.ok(
        ex_type=ex_type,
        schema_version=schema_version,
        warnings=warnings + hook_warnings,
    )
    if not _should_run_preflight(result, preflight_policy):
        return result

    preflight = run_entity_preflight(
        payload_mapping,
        lookup=entity_lookup,
        policy=preflight_policy,
    )
    return _apply_preflight(result, preflight)
