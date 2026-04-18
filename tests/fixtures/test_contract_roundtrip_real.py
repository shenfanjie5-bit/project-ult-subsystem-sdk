from __future__ import annotations

from collections.abc import Mapping

import pytest

from subsystem_sdk.fixtures import available_fixture_bundles, load_fixture_bundle
from subsystem_sdk.validate.engine import validate_payload


def _real_contracts_registry() -> Mapping[str, object]:
    contracts = pytest.importorskip("contracts")
    registry = getattr(contracts, "EX_PAYLOAD_SCHEMAS", None)
    if not isinstance(registry, Mapping):
        pytest.skip("contracts.EX_PAYLOAD_SCHEMAS is not available")
    return registry


def test_packaged_fixtures_roundtrip_with_real_contracts_when_available() -> None:
    registry = _real_contracts_registry()
    missing = {"Ex-0", "Ex-1", "Ex-2", "Ex-3"}.difference(registry)
    if missing:
        pytest.skip(f"contracts registry missing Ex schemas: {sorted(missing)!r}")

    for bundle_name in available_fixture_bundles():
        bundle = load_fixture_bundle(bundle_name)
        for example in bundle.valid_examples:
            result = validate_payload(example.payload)
            assert result.is_valid is True, (bundle_name, example.name, result)

        for example in bundle.invalid_examples:
            result = validate_payload(example.payload)
            assert result.is_valid is False, (bundle_name, example.name)
