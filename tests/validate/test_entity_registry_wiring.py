from __future__ import annotations

from collections.abc import Iterable, Mapping

import pytest

from subsystem_sdk.validate import (
    EntityRegistryLookupUnavailableError,
    LiveEntityRegistryLookup,
    build_entity_preflight_wiring,
)


class RecordingResolver:
    def __init__(self, result: Mapping[str, bool]) -> None:
        self._result = dict(result)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        self.calls.append(refs_tuple)
        return self._result


def test_live_entity_registry_lookup_calls_configured_resolver() -> None:
    resolver = RecordingResolver({"ENT_STOCK_600519.SH": True})
    lookup = LiveEntityRegistryLookup(resolver)

    result = lookup.lookup(["ENT_STOCK_600519.SH", "ENT_STOCK_000001.SZ"])

    assert resolver.calls == [("ENT_STOCK_600519.SH", "ENT_STOCK_000001.SZ")]
    assert result == {
        "ENT_STOCK_600519.SH": True,
        "ENT_STOCK_000001.SZ": False,
    }


def test_live_entity_registry_lookup_normalizes_unavailable_errors() -> None:
    def resolver(_refs: Iterable[str]) -> Mapping[str, bool]:
        raise RuntimeError("registry not configured")

    lookup = LiveEntityRegistryLookup(resolver)

    with pytest.raises(EntityRegistryLookupUnavailableError, match="not configured"):
        lookup.lookup(["ENT_STOCK_600519.SH"])


def test_production_profile_builds_fail_closed_live_wiring() -> None:
    wiring = build_entity_preflight_wiring(profile="production")

    assert isinstance(wiring.lookup, LiveEntityRegistryLookup)
    assert wiring.preflight_policy == "block"
    assert wiring.lookup_unavailable_policy == "fail"


def test_dev_profile_preserves_offline_first_unavailable_behavior() -> None:
    wiring = build_entity_preflight_wiring(profile="dev", preflight_policy="warn")

    assert wiring.lookup is None
    assert wiring.preflight_policy == "warn"
    assert wiring.lookup_unavailable_policy == "skip"


def test_entity_preflight_wiring_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="unsupported entity preflight profile"):
        build_entity_preflight_wiring(profile="staging")  # type: ignore[arg-type]
