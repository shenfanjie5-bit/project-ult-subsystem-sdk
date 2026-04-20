from __future__ import annotations

import pytest

from subsystem_sdk.fixtures import available_fixture_bundles, load_fixture_bundle
from subsystem_sdk.validate.engine import validate_payload


# Codex stage-2.7 P2 fix: this test used to gate on
# ``contracts.EX_PAYLOAD_SCHEMAS`` (a registry attribute) which the real
# published ``contracts`` (>=v0.1.2) does not export. As a result it
# silently skipped in every real-contracts environment, so the "real
# roundtrip" lane was actually empty. Switch to the SDK gateway which
# stage-2.7 taught to find Ex schemas via ``contracts.schemas`` canonical
# names (Ex0Metadata / Ex1CandidateFact / Ex2CandidateSignal /
# Ex3CandidateGraphDelta). importorskip on ``contracts.schemas`` so this
# file still skips cleanly on dev-only venvs without contracts; with the
# [contracts-schemas] extra installed it actually runs.
pytest.importorskip(
    "contracts.schemas",
    reason=(
        "contracts package not installed; install [contracts-schemas] "
        "extra to run real-contracts fixture roundtrip"
    ),
)


def _resolve_real_contracts_ex_schemas() -> dict[str, type]:
    """Resolve all 4 Ex schemas via the SDK gateway against real contracts.

    Raises pytest.fail with a clear message if any schema can't be
    resolved — this is what we want, NOT silent skip, because once the
    contracts-schemas extra is installed, missing schemas are a real
    cross-repo regression.
    """

    from subsystem_sdk._contracts import (
        SUPPORTED_EX_TYPES,
        ContractsSchemaError,
        get_ex_schema,
    )

    resolved: dict[str, type] = {}
    failures: list[str] = []
    for ex_type in SUPPORTED_EX_TYPES:
        try:
            resolved[ex_type] = get_ex_schema(ex_type)
        except ContractsSchemaError as exc:
            failures.append(f"{ex_type}: {exc}")
    if failures:
        pytest.fail(
            "SDK gateway could not resolve every Ex schema against installed "
            "contracts (contracts-schemas extra was found, so this is a real "
            f"cross-repo regression, NOT an env issue):\n  - "
            + "\n  - ".join(failures)
        )
    return resolved


def test_packaged_fixtures_roundtrip_with_real_contracts() -> None:
    """Drive every packaged fixture bundle through ``validate_payload``
    against REAL contracts (not a monkeypatched fake). Valid examples
    must pass; invalid examples must fail.

    Codex stage-2.7 P1+P2 fix: previously this test silently skipped on
    every environment that had real contracts installed, so the green-
    lane never proved real-contracts compatibility. Now it always runs
    when ``[contracts-schemas]`` is present and surfaces any SDK<->contracts
    drift immediately.
    """

    schemas = _resolve_real_contracts_ex_schemas()
    assert set(schemas) == {"Ex-0", "Ex-1", "Ex-2", "Ex-3"}

    bundles_run: list[str] = []
    for bundle_name in available_fixture_bundles():
        bundle = load_fixture_bundle(bundle_name)
        bundles_run.append(bundle_name)

        for example in bundle.valid_examples:
            result = validate_payload(example.payload)
            assert result.is_valid is True, (
                f"valid example {bundle_name}/{example.name} did not pass "
                f"validate_payload against real contracts: "
                f"field_errors={list(result.field_errors)}, "
                f"warnings={list(result.warnings)}"
            )

        for example in bundle.invalid_examples:
            result = validate_payload(example.payload)
            assert result.is_valid is False, (
                f"invalid example {bundle_name}/{example.name} unexpectedly "
                f"PASSED validate_payload — guard regression"
            )

    assert bundles_run, (
        "no fixture bundles were exercised; available_fixture_bundles "
        "returned empty"
    )
