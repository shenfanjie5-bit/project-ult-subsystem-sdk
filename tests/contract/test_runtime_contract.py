"""Contract tier — SDK public API signature stability.

Per CLAUDE.md §16: subsystem-sdk's main public contracts are
``submit(payload) -> SubmitReceipt``, ``send_heartbeat(status_payload)
-> SubmitReceipt``, and ``validate_payload(payload) -> ValidationResult``.
This tier locks the signature SHAPE so a future refactor can't silently
break consumers (subsystem-announcement / subsystem-news / orchestrator).

Pure unit-tier tests live elsewhere (tests/submit/, tests/heartbeat/,
tests/validate/) — they exercise BEHAVIOUR. This tier is contract-shape-
only; it deliberately does not call into runtime side effects.

Cross-repo alignment with ``contracts.schemas.ex_payloads`` is in the
sibling ``test_contracts_alignment.py`` (gated by ``importorskip``).
"""

from __future__ import annotations

import inspect

import subsystem_sdk
from subsystem_sdk.heartbeat import HeartbeatClient, send_heartbeat
from subsystem_sdk.submit import (
    BACKEND_KINDS,
    RESERVED_PRIVATE_KEYS,
    BackendKind,
    SubmitClient,
    SubmitReceipt,
    submit,
)
from subsystem_sdk.validate import (
    EX0_BANNED_SEMANTICS,
    EX0_SEMANTIC,
    INGEST_METADATA_FIELDS,
    PRODUCER_OWNED_REQUIRED,
    ValidationResult,
    validate_payload,
)


class TestSubmitContract:
    """``submit(payload)`` is the CLAUDE.md §16.3 producer entrypoint that
    must stay signature-stable across Lite/Full backends. It delegates to
    the runtime singleton's submit method, so the top-level signature is
    the contract."""

    def test_submit_top_level_takes_a_single_payload_positional_arg(self) -> None:
        sig = inspect.signature(submit)
        params = list(sig.parameters.values())
        assert len(params) == 1, params
        (payload_param,) = params
        assert payload_param.name == "payload"
        assert payload_param.kind in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        }
        assert payload_param.default is inspect.Parameter.empty

    def test_submit_client_method_signature_matches_top_level(self) -> None:
        # SubmitClient.submit(self, payload) — same producer-facing shape
        # as the top-level submit(payload). Iron rule: signature must be
        # identical regardless of which backend the client wraps.
        method_sig = inspect.signature(SubmitClient.submit)
        params = list(method_sig.parameters.values())
        # first param is self
        assert [p.name for p in params] == ["self", "payload"]
        payload_param = params[1]
        assert payload_param.default is inspect.Parameter.empty

    def test_submit_client_from_config_factory_exists(self) -> None:
        # CLAUDE.md §11.2: Lite/Full switch is via backend adapter
        # config, not a second submit API. from_config is the documented
        # construction path; it must exist + be a classmethod.
        assert hasattr(SubmitClient, "from_config")
        assert isinstance(
            inspect.getattr_static(SubmitClient, "from_config"), classmethod
        )


class TestSendHeartbeatContract:
    """``send_heartbeat(status_payload)`` is the Ex-0 entrypoint. Same
    signature-stability requirement as submit."""

    def test_send_heartbeat_top_level_signature(self) -> None:
        sig = inspect.signature(send_heartbeat)
        params = list(sig.parameters.values())
        assert len(params) == 1
        (status_param,) = params
        assert status_param.name == "status_payload"
        assert status_param.default is inspect.Parameter.empty

    def test_heartbeat_client_method_signature_matches_top_level(self) -> None:
        method_sig = inspect.signature(HeartbeatClient.send_heartbeat)
        params = list(method_sig.parameters.values())
        assert [p.name for p in params] == ["self", "status_payload"]


class TestValidatePayloadContract:
    """``validate_payload(payload, *, entity_lookup=None, preflight_policy='skip')
    -> ValidationResult`` is the SDK-side pre-submit validator. Producer-
    owned + ex_type derivation + semantic guards happen here, BEFORE any
    backend dispatch.
    """

    def test_validate_payload_signature(self) -> None:
        sig = inspect.signature(validate_payload)
        params = list(sig.parameters.values())
        # 1 producer-positional + 2 kw-only knobs with defaults.
        assert [p.name for p in params] == [
            "payload",
            "entity_lookup",
            "preflight_policy",
        ]
        # First param is required (no default) — anchor the producer
        # contract; the optional knobs are convenience for SubmitClient.
        payload_param = params[0]
        assert payload_param.default is inspect.Parameter.empty
        # The two optional knobs MUST stay defaulted so callers can omit
        # them — adding required params here would break consumers.
        assert params[1].default is None
        assert params[2].default == "skip"

    def test_validation_result_is_structurally_stable(self) -> None:
        # ValidationResult is a Pydantic model — fields are in
        # ``model_fields``, not class attributes. Anchor the names that
        # SubmitClient._enrich_validation + downstream consumers depend
        # on; if any go away, dispatch path breaks silently.
        fields = set(ValidationResult.model_fields)
        assert {"is_valid", "ex_type", "preflight"}.issubset(fields), (
            f"ValidationResult lost a key field; got {sorted(fields)}"
        )

    def test_validate_payload_returns_validation_result(self) -> None:
        # Sanity: actually call it to make sure the return-annotation
        # contract holds at runtime, not just per type-check. Use a
        # minimal Ex-0 payload that only exercises the SDK guards (we
        # don't need contracts model_validate to succeed for this; the
        # cross-repo align test in test_contracts_alignment.py already
        # documents that).
        result = validate_payload({"ex_type": "Ex-0"})
        assert isinstance(result, ValidationResult)
        # ex_type derivation should land on Ex-0.
        assert result.ex_type == "Ex-0"


class TestSubmitReceiptContract:
    """SubmitReceipt is the transport-neutral receipt contract. CLAUDE.md
    §5.4: must NOT expose PG / Kafka private fields to upper layers."""

    def test_receipt_has_stable_field_set(self) -> None:
        assert set(SubmitReceipt.model_fields) == {
            "accepted",
            "receipt_id",
            "backend_kind",
            "transport_ref",
            "validator_version",
            "warnings",
            "errors",
        }

    def test_receipt_extra_is_forbidden(self) -> None:
        # Pydantic ConfigDict(extra='forbid') — extra fields rejected at
        # construction. This is what enforces "no private leak" at the
        # type level (assert_no_private_leak is the runtime path).
        assert SubmitReceipt.model_config.get("extra") == "forbid"

    def test_receipt_is_frozen(self) -> None:
        assert SubmitReceipt.model_config.get("frozen") is True

    def test_backend_kinds_are_exactly_three(self) -> None:
        # Lite (lite_pg) + Full (full_kafka) + mock — adding a 4th would
        # be a Layer B contract change requiring contracts version bump.
        assert tuple(BACKEND_KINDS) == ("lite_pg", "full_kafka", "mock")
        # BackendKind is a Literal; runtime check happens via the Literal.
        # We can't introspect Literal directly here without typing tricks;
        # the union of values is asserted via BACKEND_KINDS.

    def test_reserved_private_keys_non_empty_and_disjoint_from_public_fields(
        self,
    ) -> None:
        public_fields = set(SubmitReceipt.model_fields)
        assert RESERVED_PRIVATE_KEYS, "RESERVED_PRIVATE_KEYS must list backend leaks"
        assert RESERVED_PRIVATE_KEYS.isdisjoint(public_fields), (
            f"private keys should never overlap public receipt fields: "
            f"{RESERVED_PRIVATE_KEYS & public_fields}"
        )


class TestSemanticConstantStability:
    """CLAUDE.md guard rails — these constants are referenced by
    downstream subsystems; renaming any would break them silently."""

    def test_ex0_semantic_value_is_locked(self) -> None:
        # CLAUDE.md §3 + §23: Ex-0 = Metadata / heartbeat. The single
        # canonical semantic string is the SDK's enforcement point.
        assert EX0_SEMANTIC == "metadata_or_heartbeat"

    def test_ex0_banned_semantics_cover_other_ex_types(self) -> None:
        # Must include at least these — drift = a renamed/dropped guard.
        for forbidden in ("fact", "signal", "graph_delta", "business_event"):
            assert forbidden in EX0_BANNED_SEMANTICS

    def test_ingest_metadata_fields_cover_layer_b_assignments(self) -> None:
        # CLAUDE.md term: Ingest Metadata = Layer B-assigned fields.
        # The canonical 3 are submitted_at / ingest_seq / layer_b_receipt_id.
        for ingest in ("submitted_at", "ingest_seq", "layer_b_receipt_id"):
            assert ingest in INGEST_METADATA_FIELDS

    def test_producer_owned_required_lists_all_four_ex_types(self) -> None:
        assert set(PRODUCER_OWNED_REQUIRED) == {"Ex-0", "Ex-1", "Ex-2", "Ex-3"}
        # Every Ex type must require at least subsystem_id.
        for ex_type, required in PRODUCER_OWNED_REQUIRED.items():
            assert "subsystem_id" in required, ex_type


class TestPackageVersionExposed:
    def test_version_string_is_present(self) -> None:
        assert isinstance(subsystem_sdk.__version__, str)
        assert subsystem_sdk.__version__
