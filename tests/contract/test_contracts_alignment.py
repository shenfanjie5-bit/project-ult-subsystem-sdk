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

Stage 2.7 follow-up (codex P1 fix): the SDK's ``build_ex0_payload`` ↔
contracts' ``Ex0Metadata`` round-trip used to fail for two reasons:

1. SDK output included ``ex_type``/``semantic`` envelope fields, but
   ``Ex0Metadata`` has ``extra='forbid'`` and rejected them.
2. SDK output used ``status='healthy'`` (HeartbeatState literal), but
   ``Ex0Metadata.status`` is ``contracts.core.types.HeartbeatStatus``
   which only accepts ``{ok, degraded, failed}``.

Both are now fixed at the SDK boundary:

- ``validate_payload`` strips SDK envelope (``ex_type`` / ``semantic``)
  before ``schema.model_validate`` (validate/engine.py).
- ``build_ex0_payload`` maps SDK's ``HeartbeatState`` to contracts'
  ``HeartbeatStatus`` enum on wire output via
  ``HEARTBEAT_STATE_TO_CONTRACTS_STATUS`` (heartbeat/payload.py).

The user-facing API still accepts ``"healthy"``/``"degraded"``/
``"unhealthy"`` (no breaking change to SDK callers); the wire payload
emitted to Layer B is contracts-compliant. ``TestSdkBuildEx0PayloadEndToEnd``
locks this in.
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


class TestSdkBuildEx0PayloadEndToEnd:
    """SDK builder → SDK validator → real contracts model — the path that
    used to be broken (codex stage-2.7 P1) is now locked in as a hard
    requirement. If anyone drifts the SDK envelope strip in
    ``validate/engine.py`` or the HeartbeatState→HeartbeatStatus map in
    ``heartbeat/payload.py``, this test fails immediately.
    """

    @pytest.mark.parametrize(
        "sdk_state, expected_wire_status",
        [
            ("healthy", "ok"),
            ("degraded", "degraded"),
            ("unhealthy", "failed"),
        ],
    )
    def test_sdk_build_ex0_payload_validates_against_contracts_ex0metadata(
        self, sdk_state: str, expected_wire_status: str
    ) -> None:
        from datetime import UTC, datetime

        from contracts.schemas import Ex0Metadata

        from subsystem_sdk.heartbeat.payload import build_ex0_payload

        payload = build_ex0_payload(
            subsystem_id="test-subsystem",
            version="0.0.0",
            status=sdk_state,
            heartbeat_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        # The SDK envelope (ex_type, semantic) is still present in the
        # SDK-side payload mapping for routing purposes; validate_payload
        # strips them before model_validate. Here we mirror that strip
        # to assert what contracts directly receives is wire-compliant.
        wire = {k: v for k, v in payload.items() if k not in ("ex_type", "semantic")}
        # Status must already be in contracts' HeartbeatStatus enum.
        assert wire["status"] == expected_wire_status, (
            f"build_ex0_payload(status={sdk_state!r}) emitted wire status "
            f"{wire['status']!r}; expected {expected_wire_status!r}. "
            "HEARTBEAT_STATE_TO_CONTRACTS_STATUS map drifted."
        )
        # And contracts must accept the wire payload without raising.
        validated = Ex0Metadata.model_validate(wire)
        assert validated.status.value == expected_wire_status

    def test_validate_payload_accepts_sdk_built_payload_against_real_contracts(
        self,
    ) -> None:
        # Full SDK path: build → validate. The validator strips envelope
        # internally before calling Ex0Metadata.model_validate. If
        # validate_payload returns invalid here, the SDK is shipping a
        # broken contract with Layer B (codex stage-2.7 P1).
        from datetime import UTC, datetime

        from subsystem_sdk.heartbeat.payload import build_ex0_payload
        from subsystem_sdk.validate.engine import validate_payload

        payload = build_ex0_payload(
            subsystem_id="test-subsystem",
            version="0.0.0",
            status="healthy",
            heartbeat_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        result = validate_payload(payload)
        assert result.is_valid, (
            f"validate_payload rejected SDK-built Ex-0 against real "
            f"contracts; field_errors={list(result.field_errors)}"
        )
        assert result.ex_type == "Ex-0"

    def test_send_heartbeat_round_trip_returns_accepted_against_real_contracts(
        self,
    ) -> None:
        # End-to-end: build → validate → dispatch through MockSubmitBackend.
        # This is the exact path codex reproduced as broken. Now must
        # come back with receipt.accepted=True + zero errors.
        from datetime import UTC, datetime

        from subsystem_sdk.backends.heartbeat import (
            SubmitBackendHeartbeatAdapter,
        )
        from subsystem_sdk.backends.mock import MockSubmitBackend
        from subsystem_sdk.heartbeat.client import HeartbeatClient
        from subsystem_sdk.heartbeat.payload import build_ex0_payload

        backend = MockSubmitBackend()
        client = HeartbeatClient(SubmitBackendHeartbeatAdapter(backend))
        payload = build_ex0_payload(
            subsystem_id="test-subsystem",
            version="0.0.0",
            status="healthy",
            heartbeat_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        receipt = client.send_heartbeat(payload)
        assert receipt.accepted, (
            f"send_heartbeat did not accept SDK-built Ex-0 against real "
            f"contracts; errors={list(receipt.errors)}"
        )
        assert receipt.errors == ()

    def test_backend_receives_wire_shape_not_sdk_envelope(self) -> None:
        # Stage-2.7 follow-up #2 (codex review #2 P1): the SDK envelope
        # (ex_type/semantic/produced_at) MUST be stripped at the dispatch
        # boundary too — not only at validate. Otherwise PG/Kafka serialize
        # the envelope onto the wire and Layer B ingest rejects it.
        # End-to-end check: drive a real heartbeat through the SDK and
        # assert the MockSubmitBackend (proxied via SubmitBackendHeartbeatAdapter)
        # records the WIRE shape. Then round-trip that recorded shape through
        # the real contracts.schemas.Ex0Metadata model — proves Layer B
        # would accept it without further transformation.
        from datetime import UTC, datetime

        from contracts.schemas import Ex0Metadata

        from subsystem_sdk.backends.heartbeat import (
            SubmitBackendHeartbeatAdapter,
        )
        from subsystem_sdk.backends.mock import MockSubmitBackend
        from subsystem_sdk.heartbeat.client import HeartbeatClient
        from subsystem_sdk.heartbeat.payload import build_ex0_payload

        backend = MockSubmitBackend()
        client = HeartbeatClient(SubmitBackendHeartbeatAdapter(backend))
        payload = build_ex0_payload(
            subsystem_id="wire-shape-test",
            version="0.0.0",
            status="healthy",
            heartbeat_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        receipt = client.send_heartbeat(payload)
        assert receipt.accepted

        # Backend recorded exactly one payload, and it must NOT contain
        # any SDK envelope fields.
        assert len(backend.submitted_payloads) == 1
        wire_payload = backend.submitted_payloads[0]
        for envelope_field in ("ex_type", "semantic", "produced_at"):
            assert envelope_field not in wire_payload, (
                f"SDK envelope field {envelope_field!r} leaked to backend "
                f"({wire_payload!r}); validate_then_dispatch must strip the "
                "envelope BEFORE calling backend.submit/send, otherwise PG/"
                "Kafka serialize the SDK shape onto the wire and Layer B "
                "rejects it (codex stage-2.7 review #2 P1)."
            )

        # Cross-prove: the wire shape that reached the backend round-trips
        # through real contracts.schemas.Ex0Metadata without modification.
        validated = Ex0Metadata.model_validate(wire_payload)
        assert validated.subsystem_id == "wire-shape-test"
        assert validated.status.value == "ok"
