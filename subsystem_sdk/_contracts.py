"""Gateway for contract schema imports.

This module is the only SDK boundary that may load ``contracts``.  It resolves
model classes without defining Ex payload fields locally, keeping contracts as
the single schema source of truth.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from types import ModuleType
from typing import Any, Final

SUPPORTED_EX_TYPES: tuple[str, ...] = ("Ex-0", "Ex-1", "Ex-2", "Ex-3")
_SCHEMA_REGISTRY_NAMES: Final[tuple[str, ...]] = (
    "EX_SCHEMAS",
    "EX_PAYLOAD_SCHEMAS",
    "EX_PAYLOAD_MODELS",
    "SCHEMAS",
)
# The real ``contracts`` package (>=v0.1.2) exports Ex payload models from
# ``contracts.schemas`` under their canonical class names, NOT under the
# ``Ex0Payload`` / ``Ex0Schema`` shape this gateway used to look for.
# Keep this map in sync with ``contracts/src/contracts/schemas/ex_payloads.py``.
# Cross-repo align tests (tests/contract/test_contracts_alignment.py) verify
# every value here actually resolves against the installed contracts package.
_CONTRACTS_SCHEMAS_CANONICAL_NAMES: Final[dict[str, str]] = {
    "Ex-0": "Ex0Metadata",
    "Ex-1": "Ex1CandidateFact",
    "Ex-2": "Ex2CandidateSignal",
    "Ex-3": "Ex3CandidateGraphDelta",
}


class ContractsUnavailableError(RuntimeError):
    """Raised when the contracts package cannot be imported."""


class UnknownExTypeError(ValueError):
    """Raised when a caller asks for an unsupported Ex type."""


class ContractsSchemaError(RuntimeError):
    """Raised when a supported Ex type cannot be resolved to a schema class."""


def _load_contracts_module() -> ModuleType:
    try:
        return importlib.import_module("contracts")
    except ImportError as exc:
        raise ContractsUnavailableError(
            "contracts package is not available; "
            "install contracts to validate Ex payloads"
        ) from exc


def _candidate_schema_names(ex_type: str) -> tuple[str, ...]:
    compact = ex_type.replace("-", "")
    underscore = ex_type.replace("-", "_")
    return (
        compact,
        compact.upper(),
        f"{compact}Payload",
        f"{compact}PayloadSchema",
        f"{compact}Schema",
        f"{compact}Model",
        underscore,
        underscore.upper(),
    )


def _lookup_schema_registry(module: ModuleType, ex_type: str) -> type | None:
    for registry_name in _SCHEMA_REGISTRY_NAMES:
        registry = getattr(module, registry_name, None)
        if not isinstance(registry, Mapping):
            continue
        schema = registry.get(ex_type)
        if schema is not None:
            return schema
    return None


def _lookup_schema_attr(module: ModuleType, ex_type: str) -> type | None:
    for schema_name in _candidate_schema_names(ex_type):
        schema = getattr(module, schema_name, None)
        if schema is not None:
            return schema
    return None


def _validate_schema_type(ex_type: str, schema: Any) -> type:
    if not isinstance(schema, type):
        raise ContractsSchemaError(
            f"contracts schema for {ex_type!r} is not a model class"
        )
    if not callable(getattr(schema, "model_validate", None)):
        raise ContractsSchemaError(
            f"contracts schema for {ex_type!r} does not expose "
            "Pydantic v2 model_validate"
        )
    return schema


def _lookup_canonical_schemas_namespace(ex_type: str) -> type | None:
    """Resolve the Ex schema by importing ``contracts.schemas`` and looking
    up the canonical class name (e.g. ``Ex0Metadata``).

    This is the path the real published contracts package (>=v0.1.2) takes;
    earlier lookups (registry / get_ex_schema callable / sibling attribute
    on top-level ``contracts``) are kept for backward compatibility with
    older or test-stubbed contracts modules.
    """

    canonical_name = _CONTRACTS_SCHEMAS_CANONICAL_NAMES.get(ex_type)
    if canonical_name is None:
        return None
    try:
        schemas_module = importlib.import_module("contracts.schemas")
    except ImportError:
        return None
    return getattr(schemas_module, canonical_name, None)


def get_ex_schema(ex_type: str) -> type:
    """Return the contracts Pydantic model class for a supported Ex type."""

    if ex_type not in SUPPORTED_EX_TYPES:
        raise UnknownExTypeError(f"unsupported Ex type: {ex_type!r}")

    contracts_module = _load_contracts_module()
    schema = _lookup_schema_registry(contracts_module, ex_type)
    if schema is None:
        schema = _lookup_schema_attr(contracts_module, ex_type)
    if schema is None:
        loader = getattr(contracts_module, "get_ex_schema", None)
        if callable(loader):
            schema = loader(ex_type)
    if schema is None:
        # Real published contracts (>=v0.1.2): canonical-name lookup in
        # ``contracts.schemas``. Done last so tests that monkey-patch
        # ``sys.modules["contracts"]`` keep priority.
        schema = _lookup_canonical_schemas_namespace(ex_type)

    if schema is None:
        raise ContractsSchemaError(
            f"contracts schema for {ex_type!r} could not be resolved"
        )

    return _validate_schema_type(ex_type, schema)


def _read_model_field_default(schema: type, field_name: str) -> Any:
    model_fields = getattr(schema, "model_fields", None)
    if not isinstance(model_fields, Mapping):
        return None

    field = model_fields.get(field_name)
    if field is None:
        return None

    return getattr(field, "default", None)


def get_schema_version(schema: type) -> str:
    """Return a stable contracts schema version string."""

    for attr_name in ("schema_version", "SCHEMA_VERSION"):
        value = getattr(schema, attr_name, None)
        if isinstance(value, str) and value:
            return value

    model_config = getattr(schema, "model_config", None)
    if isinstance(model_config, Mapping):
        value = model_config.get("schema_version")
        if isinstance(value, str) and value:
            return value

    field_default = _read_model_field_default(schema, "schema_version")
    if isinstance(field_default, str) and field_default:
        return field_default

    return "unknown"
