"""Optional entity reference preflight checks for produced Ex payloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

PreflightPolicy = Literal["warn", "block", "skip"]

_PREFLIGHT_POLICIES: Final[frozenset[str]] = frozenset({"warn", "block", "skip"})
_EX_TYPE_FIELD: Final[str] = "ex_type"
_EX0_TYPE: Final[str] = "Ex-0"
PREFLIGHT_EX_TYPES: Final[frozenset[str]] = frozenset({"Ex-1", "Ex-2", "Ex-3"})
_EX0_SCHEMA_MARKERS: Final[frozenset[str]] = frozenset(
    {"heartbeat_at", "last_output_at", "pending_count"}
)
_ENTITY_REF_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "canonical_entity_id",
        "entity_id",
        "entity_ref",
        "entity_refs",
        "source_entity_id",
        "target_entity_id",
        "subject_entity_id",
        "object_entity_id",
    }
)


class EntityRegistryLookup(Protocol):
    """Minimum lookup contract required by entity preflight."""

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        """Return whether each entity reference is known."""


def _coerce_string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")
    if not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings")

    coerced = tuple(value)
    if not all(isinstance(item, str) for item in coerced):
        raise TypeError(f"{field_name} must contain only strings")
    return coerced


class EntityPreflightResult(BaseModel):
    """Entity reference preflight outcome for optional validation enrichment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checked: bool
    unresolved_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    policy: PreflightPolicy

    @field_validator("unresolved_refs", "warnings", mode="before")
    @classmethod
    def _coerce_tuple_fields(
        cls, value: Any, info: ValidationInfo
    ) -> tuple[str, ...]:
        return _coerce_string_tuple(value, field_name=info.field_name)

    @property
    def has_unresolved_refs(self) -> bool:
        """Whether any checked reference could not be resolved."""

        return bool(self.unresolved_refs)

    @property
    def should_block(self) -> bool:
        """Whether the configured policy should block on unresolved refs."""

        return self.policy == "block" and self.has_unresolved_refs

    def to_validation_preflight(self) -> dict[str, Any]:
        """Return a JSON-safe representation for ValidationResult.preflight."""

        return {
            "checked": self.checked,
            "unresolved_refs": list(self.unresolved_refs),
            "warnings": list(self.warnings),
            "policy": self.policy,
        }


def _as_mapping(payload: Mapping[str, Any] | BaseModel) -> Mapping[str, Any] | None:
    if isinstance(payload, BaseModel):
        dumped = payload.model_dump(mode="python")
        if isinstance(dumped, Mapping):
            return dumped
        return None

    if isinstance(payload, Mapping):
        return payload

    return None


def identify_preflight_ex_type(payload: Mapping[str, Any]) -> str | None:
    """Return the payload Ex type relevant to entity preflight, if recognized."""

    ex_type = payload.get(_EX_TYPE_FIELD)
    if isinstance(ex_type, str):
        if ex_type == _EX0_TYPE or ex_type in PREFLIGHT_EX_TYPES:
            return ex_type
        return None

    if ex_type is None and set(payload).intersection(_EX0_SCHEMA_MARKERS):
        return _EX0_TYPE

    return None


def _append_ref(value: str, refs: list[str], seen: set[str]) -> None:
    if value in seen:
        return
    seen.add(value)
    refs.append(value)


def _collect_ref_values(value: Any, refs: list[str], seen: set[str]) -> None:
    if isinstance(value, str):
        _append_ref(value, refs, seen)
        return

    if isinstance(value, Mapping):
        for item in value.values():
            _collect_ref_values(item, refs, seen)
        return

    if isinstance(value, (list, tuple)):
        for item in value:
            _collect_ref_values(item, refs, seen)


def _scan_for_entity_refs(value: Any, refs: list[str], seen: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _ENTITY_REF_FIELDS:
                _collect_ref_values(item, refs, seen)
            else:
                _scan_for_entity_refs(item, refs, seen)
        return

    if isinstance(value, (list, tuple)):
        for item in value:
            _scan_for_entity_refs(item, refs, seen)


def extract_entity_refs(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Extract entity reference values using the shared preflight scan policy."""

    refs: list[str] = []
    seen: set[str] = set()
    _scan_for_entity_refs(payload, refs, seen)
    return tuple(refs)


def should_run_entity_preflight(
    *,
    is_valid: bool,
    ex_type: str,
    policy: PreflightPolicy,
) -> bool:
    """Return whether an already validated payload should run entity preflight."""

    return is_valid and ex_type in PREFLIGHT_EX_TYPES and policy != "skip"


def _skip_result(warning: str) -> EntityPreflightResult:
    return EntityPreflightResult(
        checked=False,
        unresolved_refs=(),
        warnings=(warning,),
        policy="skip",
    )


def _coerce_policy(policy: PreflightPolicy) -> PreflightPolicy:
    if policy not in _PREFLIGHT_POLICIES:
        raise ValueError(f"unsupported entity preflight policy: {policy!r}")
    return cast(PreflightPolicy, policy)


def run_entity_preflight(
    payload: Mapping[str, Any] | BaseModel,
    *,
    lookup: EntityRegistryLookup | None = None,
    policy: PreflightPolicy = "warn",
) -> EntityPreflightResult:
    """Run optional entity ref lookup before Ex-1/2/3 submission."""

    effective_policy = _coerce_policy(policy)
    payload_mapping = _as_mapping(payload)
    if payload_mapping is None:
        return _skip_result(
            "entity preflight skipped: payload is not a mapping or Pydantic BaseModel"
        )

    ex_type = identify_preflight_ex_type(payload_mapping)
    if ex_type == _EX0_TYPE:
        return _skip_result("entity preflight skipped for Ex-0 heartbeat payload")
    if ex_type not in PREFLIGHT_EX_TYPES:
        return _skip_result(
            "entity preflight skipped: payload is not a recognized Ex-1/Ex-2/Ex-3 "
            "payload"
        )
    if effective_policy == "skip":
        return _skip_result("entity preflight skipped by policy")
    if lookup is None:
        return _skip_result("entity preflight skipped: no lookup channel provided")

    refs = extract_entity_refs(payload_mapping)
    if not refs:
        return EntityPreflightResult(
            checked=True,
            unresolved_refs=(),
            warnings=(),
            policy=effective_policy,
        )

    try:
        lookup_result = lookup.lookup(refs)
    except Exception as exc:  # pragma: no cover - exact registry failures vary.
        return _skip_result(f"entity preflight skipped: lookup channel failed: {exc}")

    if not isinstance(lookup_result, Mapping):
        return _skip_result(
            "entity preflight skipped: lookup channel returned a non-mapping result"
        )

    unresolved: list[str] = []
    malformed: list[str] = []
    for ref in refs:
        resolved = lookup_result.get(ref)
        if resolved is True:
            continue
        unresolved.append(ref)
        if resolved is not None and not isinstance(resolved, bool):
            malformed.append(ref)

    unresolved_refs = tuple(unresolved)
    warnings_list: list[str] = []
    if malformed:
        refs_text = ", ".join(malformed)
        warnings_list.append(
            "entity preflight lookup returned non-bool resolution value(s) "
            f"for reference(s): {refs_text}"
        )
    if unresolved_refs:
        refs_text = ", ".join(unresolved_refs)
        warnings_list.append(
            f"entity preflight found unresolved reference(s): {refs_text}"
        )

    return EntityPreflightResult(
        checked=True,
        unresolved_refs=unresolved_refs,
        warnings=tuple(warnings_list),
        policy=effective_policy,
    )
