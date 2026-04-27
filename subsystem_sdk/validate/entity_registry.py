"""Live entity-registry lookup wiring for production preflight."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal, cast

from subsystem_sdk.validate.preflight import (
    EntityRegistryLookup,
    LookupUnavailablePolicy,
    PreflightPolicy,
)

EntityPreflightProfile = Literal["dev", "production"]

_ENTITY_PREFLIGHT_PROFILES: Final[frozenset[str]] = frozenset(
    {"dev", "production"}
)


class EntityRegistryLookupUnavailableError(RuntimeError):
    """Raised when the bundled live entity-registry lookup cannot be used."""


class LiveEntityRegistryLookup:
    """Lookup adapter backed by entity-registry's configured live repository."""

    def __init__(
        self,
        resolver: Callable[[Iterable[str]], Mapping[str, bool]] | None = None,
    ) -> None:
        self._resolver = resolver or _default_entity_registry_resolver

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        try:
            result = self._resolver(refs_tuple)
        except Exception as exc:
            raise EntityRegistryLookupUnavailableError(
                f"live entity-registry lookup failed: {exc}"
            ) from exc

        if not isinstance(result, Mapping):
            raise EntityRegistryLookupUnavailableError(
                "live entity-registry lookup returned a non-mapping result"
            )
        return {ref: result.get(ref) is True for ref in refs_tuple}


@dataclass(frozen=True)
class EntityPreflightWiring:
    """Resolved preflight knobs for SubmitClient construction."""

    lookup: EntityRegistryLookup | None
    preflight_policy: PreflightPolicy
    lookup_unavailable_policy: LookupUnavailablePolicy


def build_entity_preflight_wiring(
    *,
    profile: EntityPreflightProfile = "dev",
    entity_lookup: EntityRegistryLookup | None = None,
    preflight_policy: PreflightPolicy = "skip",
) -> EntityPreflightWiring:
    """Resolve dev/production entity preflight behavior.

    Dev mode preserves the SDK's historical offline-first behavior. Production
    mode always requires a lookup channel, blocks unresolved refs, and treats
    lookup absence or runtime failure as a fail-closed validation error.
    """

    effective_profile = _coerce_profile(profile)
    if effective_profile == "production":
        return EntityPreflightWiring(
            lookup=entity_lookup or LiveEntityRegistryLookup(),
            preflight_policy="block",
            lookup_unavailable_policy="fail",
        )
    return EntityPreflightWiring(
        lookup=entity_lookup,
        preflight_policy=preflight_policy,
        lookup_unavailable_policy="skip",
    )


def _coerce_profile(profile: EntityPreflightProfile) -> EntityPreflightProfile:
    if profile not in _ENTITY_PREFLIGHT_PROFILES:
        raise ValueError(f"unsupported entity preflight profile: {profile!r}")
    return cast(EntityPreflightProfile, profile)


def _default_entity_registry_resolver(refs: Iterable[str]) -> Mapping[str, bool]:
    try:
        from entity_registry import lookup_entity_refs
    except ImportError as exc:
        raise EntityRegistryLookupUnavailableError(
            "project-ult-entity-registry is not importable; configure the "
            "production environment with entity-registry on PYTHONPATH or pass "
            "an injected EntityRegistryLookup"
        ) from exc

    return lookup_entity_refs(refs)
