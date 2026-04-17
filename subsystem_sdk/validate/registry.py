"""Weak producer-side validation hooks."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES, UnknownExTypeError

ValidationHook = Callable[[Mapping[str, Any]], Sequence[str]]


def _assert_supported_ex_type(ex_type: str) -> None:
    if ex_type not in SUPPORTED_EX_TYPES:
        raise UnknownExTypeError(f"unsupported Ex type: {ex_type!r}")


def _coerce_hook_warnings(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError("validation hooks must return a sequence of warning strings")

    warnings = tuple(value)
    if not all(isinstance(item, str) for item in warnings):
        raise TypeError("validation hooks must return only warning strings")
    return warnings


@dataclass(frozen=True, slots=True)
class ValidatorRegistry:
    """Registry for non-authoritative producer-side warning hooks."""

    _hooks: dict[str, list[ValidationHook]] = field(
        default_factory=lambda: {ex_type: [] for ex_type in SUPPORTED_EX_TYPES}
    )

    def register_hook(self, ex_type: str, hook: ValidationHook) -> None:
        _assert_supported_ex_type(ex_type)
        if not callable(hook):
            raise TypeError("validation hook must be callable")
        self._hooks.setdefault(ex_type, []).append(hook)

    def run_hooks(self, ex_type: str, payload: Mapping[str, Any]) -> tuple[str, ...]:
        _assert_supported_ex_type(ex_type)

        warnings: list[str] = []
        for hook in tuple(self._hooks.get(ex_type, ())):
            warnings.extend(_coerce_hook_warnings(hook(payload)))
        return tuple(warnings)


_DEFAULT_REGISTRY = ValidatorRegistry()


def register_hook(ex_type: str, hook: ValidationHook) -> None:
    """Register a warning-only hook on the default validation registry."""

    _DEFAULT_REGISTRY.register_hook(ex_type, hook)


def run_hooks(ex_type: str, payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Run warning-only hooks from the default validation registry."""

    return _DEFAULT_REGISTRY.run_hooks(ex_type, payload)


__all__ = [
    "ValidationHook",
    "ValidatorRegistry",
    "register_hook",
    "run_hooks",
]
