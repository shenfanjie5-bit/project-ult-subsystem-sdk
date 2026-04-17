"""Human-readable validation reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from subsystem_sdk.validate.result import ValidationResult


def _coerce_string_items(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, bytes):
        return (value.decode("utf-8", errors="replace"),)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return (str(value),)


def _append_list_section(
    lines: list[str],
    title: str,
    items: Sequence[str],
    *,
    indent: str = "  ",
) -> None:
    lines.append(f"{title}:")
    if not items:
        lines.append(f"{indent}- none")
        return
    for item in items:
        lines.append(f"{indent}- {item}")


def _append_preflight_section(
    lines: list[str], preflight: Mapping[str, Any] | None
) -> None:
    lines.append("preflight:")
    if preflight is None:
        lines.append("  checked: false")
        lines.append("  policy: none")
        lines.append("  unresolved_refs:")
        lines.append("    - none")
        lines.append("  warnings:")
        lines.append("    - none")
        return

    checked = bool(preflight.get("checked", False))
    policy = str(preflight.get("policy", "unknown"))
    unresolved_refs = _coerce_string_items(preflight.get("unresolved_refs"))
    warnings = _coerce_string_items(preflight.get("warnings"))

    lines.append(f"  checked: {str(checked).lower()}")
    lines.append(f"  policy: {policy}")
    _append_list_section(lines, "  unresolved_refs", unresolved_refs, indent="    ")
    _append_list_section(lines, "  warnings", warnings, indent="    ")


def richer_validation_report(result: ValidationResult) -> str:
    """Return a deterministic human-readable validation report."""

    lines = [
        "Validation Report",
        f"ex_type: {result.ex_type}",
        f"schema_version: {result.schema_version}",
        f"status: {'valid' if result.is_valid else 'invalid'}",
    ]
    _append_list_section(lines, "field_errors", result.field_errors)
    _append_list_section(lines, "warnings", result.warnings)
    _append_preflight_section(lines, result.preflight)
    return "\n".join(lines)
