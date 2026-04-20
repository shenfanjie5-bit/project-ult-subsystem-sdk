"""Cross-repo alignment: subsystem-sdk runtime guards ↔ contracts.schemas
Ex payload models. CLAUDE.md (subsystem-sdk + contracts both): Ex schemas
are defined ONLY in ``contracts``; the SDK's local validators / semantic
guards must stay synced with what contracts ships.

Module-level skip on missing dep — install [contracts-schemas] extra to
run this lane:

    pip install -e ".[dev,contracts-schemas]"
    pytest tests/contract/test_contracts_alignment.py

Three invariants:

1. Every ``SUPPORTED_EX_TYPES`` entry resolves through the SDK gateway
   (``subsystem_sdk._contracts.get_ex_schema``) to a real Pydantic model
   in ``contracts.schemas`` — proving the canonical-name lookup we added
   in stage 2.7's _contracts.py fix actually finds the published classes
   (Ex0Metadata / Ex1CandidateFact / Ex2CandidateSignal /
   Ex3CandidateGraphDelta).
2. SDK's ``INGEST_METADATA_FIELDS`` (subsystem_sdk.validate.semantics) is
   a SUPERSET of contracts' ``FORBIDDEN_INGEST_METADATA_FIELDS`` — if
   contracts ever expands the forbidden set, the SDK guard must keep up.
3. Every Ex schema in contracts has ``BaseExPayload``'s
   ``reject_ingest_metadata`` validator wired (cross-checked by an
   actual instantiation attempt with a forbidden field).

What this tier does NOT test (out of stage 2.7 scope, documented for
future work): the SDK's ``build_ex0_payload`` produces a payload with
``ex_type``/``semantic`` wrapper fields and uses the SDK's HeartbeatState
literal ({healthy,degraded,unhealthy}), but contracts' ``Ex0Metadata``
uses ``HeartbeatStatus`` ({ok,degraded,failed}) and rejects extras. Real
SDK→contracts model_validate today FAILS for that reason. This is a
known cross-repo design tension that needs an SDK-side payload shape
refactor in a separate milestone, not a stage-2 test-baseline change.
"""

from __future__ import annotations

import pytest

contracts_schemas = pytest.importorskip(
    "contracts.schemas",
    reason=(
        "contracts package not installed; run `pip install -e "
        '".[dev,contracts-schemas]"` to enable cross-repo alignment '
        "tests"
    ),
)


class TestSupportedExTypesResolveAgainstContracts:
    """Iron rule #4 (cross-repo align): every SDK-supported Ex type must
    resolve via the gateway to a real contracts.schemas model class."""

    def test_every_supported_ex_type_resolves(self) -> None:
        from contracts.schemas import (
            Ex0Metadata,
            Ex1CandidateFact,
            Ex2CandidateSignal,
            Ex3CandidateGraphDelta,
        )

        from subsystem_sdk._contracts import SUPPORTED_EX_TYPES, get_ex_schema

        expected = {
            "Ex-0": Ex0Metadata,
            "Ex-1": Ex1CandidateFact,
            "Ex-2": Ex2CandidateSignal,
            "Ex-3": Ex3CandidateGraphDelta,
        }
        assert set(SUPPORTED_EX_TYPES) == set(expected)

        for ex_type, expected_model in expected.items():
            resolved = get_ex_schema(ex_type)
            assert resolved is expected_model, (
                f"SDK gateway resolved {ex_type!r} to {resolved!r}, "
                f"expected {expected_model!r}"
            )

    def test_canonical_name_map_in_sync_with_contracts_schemas_exports(self) -> None:
        # Stage 2.7 added _CONTRACTS_SCHEMAS_CANONICAL_NAMES in _contracts.py.
        # If that map drifts from the actual class names contracts.schemas
        # exports, the gateway will silently fall through to "schema not
        # resolved". Cross-validate.
        from contracts import schemas as contracts_schemas_module

        from subsystem_sdk._contracts import (
            _CONTRACTS_SCHEMAS_CANONICAL_NAMES,
        )

        for ex_type, canonical_name in _CONTRACTS_SCHEMAS_CANONICAL_NAMES.items():
            assert hasattr(contracts_schemas_module, canonical_name), (
                f"_CONTRACTS_SCHEMAS_CANONICAL_NAMES claims {ex_type!r} -> "
                f"{canonical_name!r}, but contracts.schemas has no "
                f"such attribute. Update the map or rename the contracts "
                "class — they must agree."
            )


class TestIngestMetadataGuardsAligned:
    """Iron rule: SDK's INGEST_METADATA_FIELDS must be a superset of
    contracts' FORBIDDEN_INGEST_METADATA_FIELDS, so the SDK never lets
    through a field contracts will reject.
    """

    def test_sdk_forbidden_set_is_superset_of_contracts_set(self) -> None:
        from contracts.schemas import FORBIDDEN_INGEST_METADATA_FIELDS

        from subsystem_sdk.validate.semantics import INGEST_METADATA_FIELDS

        missing = set(FORBIDDEN_INGEST_METADATA_FIELDS) - set(
            INGEST_METADATA_FIELDS
        )
        assert not missing, (
            f"SDK's INGEST_METADATA_FIELDS missing fields contracts already "
            f"forbids: {sorted(missing)}. The SDK guard would let these "
            "through to the contracts model where they'd be rejected — "
            "drift creates a confusing two-layer error."
        )

    def test_contracts_base_ex_payload_has_reject_ingest_metadata_validator(
        self,
    ) -> None:
        # Behavioural cross-check: building an Ex-0 payload that includes
        # `submitted_at` MUST raise (the BaseExPayload pre-model-validator
        # is what enforces this on the contracts side). If this stops
        # raising, the SDK guard is no longer the only safety net.
        from contracts.schemas import Ex0Metadata
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Ex0Metadata.model_validate(
                {
                    "subsystem_id": "test-subsystem",
                    "version": "0.0.0",
                    "heartbeat_at": "2026-01-01T00:00:00Z",
                    "status": "ok",
                    "last_output_at": None,
                    "pending_count": 0,
                    "submitted_at": "2026-01-01T00:00:00Z",  # forbidden
                }
            )


class TestKnownDesignTensionDocumented:
    """Document the SDK ↔ contracts model_validate mismatch that public.py's
    smoke hook deliberately works around. Once an SDK refactor reconciles
    payload shape + status enum, REMOVE these xfail tests — they are
    drift detectors, not goal posts.
    """

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known stage-2.7 cross-repo design tension: SDK's "
            "build_ex0_payload wraps with ex_type/semantic + uses "
            "{healthy,degraded,unhealthy} HeartbeatState. contracts' "
            "Ex0Metadata rejects extras + uses {ok,degraded,failed} "
            "HeartbeatStatus. Reconciling needs a separate SDK milestone, "
            "not stage 2 test-baseline. xfail strict=True so the day "
            "someone fixes it, this test starts passing and yells at us "
            "to remove the xfail (and the smoke-hook workaround)."
        ),
    )
    def test_sdk_build_ex0_payload_validates_against_contracts_ex0metadata(
        self,
    ) -> None:
        from datetime import UTC, datetime

        from contracts.schemas import Ex0Metadata

        from subsystem_sdk.heartbeat.payload import build_ex0_payload

        payload = build_ex0_payload(
            subsystem_id="test-subsystem",
            version="0.0.0",
            status="healthy",
            heartbeat_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        # Currently raises pydantic.ValidationError because:
        # - "ex_type"/"semantic" are extras (forbidden on Ex0Metadata)
        # - "healthy" not in {"ok", "degraded", "failed"}
        Ex0Metadata.model_validate(payload)
