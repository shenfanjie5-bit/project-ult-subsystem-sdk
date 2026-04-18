"""Internal helpers for JSON-like defensive copies and immutable snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any


def copy_json_like(value: Any) -> Any:
    """Return a mutable JSON-safe copy of nested container values."""

    if isinstance(value, Mapping):
        return {str(key): copy_json_like(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [copy_json_like(item) for item in value]
    if isinstance(value, set | frozenset):
        return [copy_json_like(item) for item in sorted(value, key=repr)]
    return deepcopy(value)


def freeze_json_like(value: Any) -> Any:
    """Return an immutable snapshot of nested JSON-like container values."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): freeze_json_like(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(freeze_json_like(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(freeze_json_like(item) for item in value)
    return deepcopy(value)


def to_json_safe(value: Any) -> Any:
    """Return nested values in JSON-serializable container types."""

    if isinstance(value, Mapping):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, frozenset | set):
        return [to_json_safe(item) for item in sorted(value, key=repr)]
    return value
