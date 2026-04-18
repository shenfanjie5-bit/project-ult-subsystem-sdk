"""Subsystem SDK package scaffold for project doc section 1."""

from subsystem_sdk.validate import (
    EntityPreflightResult,
    EntityRegistryLookup,
    PreflightPolicy,
    run_entity_preflight,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "EntityPreflightResult",
    "EntityRegistryLookup",
    "PreflightPolicy",
    "run_entity_preflight",
]
