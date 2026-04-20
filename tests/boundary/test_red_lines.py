"""Boundary tier — CLAUDE.md red lines that subsystem-sdk MUST enforce.

Five red lines per ``subsystem-sdk/CLAUDE.md`` "不可协商约束":

1. **Ex-0 semantic locked** — `Ex-0` must remain `metadata_or_heartbeat`;
   any other declared semantic must raise `Ex0SemanticError`.
2. **No ingest metadata in producer payload** — `submitted_at`,
   `ingest_seq`, `layer_b_receipt_id` must be rejected at the SDK
   guard, in any of the 4 Ex types.
3. **Lite/Full submit signature parity** — `SubmitClient.submit` and the
   top-level `submit` must have identical signature regardless of which
   backend is wrapped.
4. **No backend-private leak in receipts** — `RESERVED_PRIVATE_KEYS`
   (pg_queue_id / kafka_offset / ...) must be rejected before normalizing
   into `SubmitReceipt`.
5. **public.py boundary clean** — subprocess-isolated deny scan: the
   public.py module must not pull in heavy infra (PG / Kafka / orchestrator
   / contracts.io) at import time.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


# ── Red line #1: Ex-0 semantic locked ────────────────────────────────


class TestEx0SemanticLocked:
    """CLAUDE.md §3 + §23 + audit checklist #4: `Ex-0` 仍保持 Metadata /
    心跳语义，没有被赋予其他业务含义.
    """

    def test_assert_ex0_semantic_accepts_canonical_value(self) -> None:
        from subsystem_sdk.validate.semantics import (
            EX0_SEMANTIC,
            assert_ex0_semantic,
        )

        # Should not raise.
        assert_ex0_semantic(EX0_SEMANTIC)

    @pytest.mark.parametrize(
        "wrong_semantic",
        ["fact", "signal", "graph_delta", "business_event", "metadata", ""],
    )
    def test_assert_ex0_semantic_rejects_anything_else(
        self, wrong_semantic: str
    ) -> None:
        from subsystem_sdk.validate.semantics import (
            Ex0SemanticError,
            assert_ex0_semantic,
        )

        with pytest.raises(Ex0SemanticError):
            assert_ex0_semantic(wrong_semantic)


# ── Red line #2: no ingest metadata in producer payload ──────────────


class TestNoIngestMetadataInProducerPayload:
    """CLAUDE.md §3 + §5.4 + audit checklist #2: `submitted_at` /
    `ingest_seq` / `layer_b_receipt_id` 不进入 producer payload.
    """

    @pytest.mark.parametrize(
        "forbidden_field",
        ["submitted_at", "ingest_seq", "layer_b_receipt_id"],
    )
    def test_assert_no_ingest_metadata_rejects_each_forbidden_field(
        self, forbidden_field: str
    ) -> None:
        from subsystem_sdk.validate.semantics import (
            IngestMetadataLeakError,
            assert_no_ingest_metadata,
        )

        # Top-level leak.
        with pytest.raises(IngestMetadataLeakError) as excinfo:
            assert_no_ingest_metadata(
                {
                    "subsystem_id": "boundary-test",
                    forbidden_field: "leak",
                }
            )
        assert forbidden_field in str(excinfo.value)

    @pytest.mark.parametrize(
        "forbidden_field",
        ["submitted_at", "ingest_seq", "layer_b_receipt_id"],
    )
    def test_assert_no_ingest_metadata_catches_one_level_nested_leak(
        self, forbidden_field: str
    ) -> None:
        # CLAUDE.md: "Reject ingest metadata at the payload top level or
        # one nested mapping level." Anchor that nested-level guard so a
        # refactor doesn't regress it to top-level only.
        from subsystem_sdk.validate.semantics import (
            IngestMetadataLeakError,
            assert_no_ingest_metadata,
        )

        with pytest.raises(IngestMetadataLeakError):
            assert_no_ingest_metadata(
                {
                    "subsystem_id": "boundary-test",
                    "fact_content": {forbidden_field: "leak"},
                }
            )


# ── Red line #3: Lite/Full submit signature parity ───────────────────


class TestLiteFullSubmitSignatureParity:
    """CLAUDE.md §5.4 + §16.3 + audit checklist #3: `submit()` /
    `send_heartbeat()` 签名是否仍对 Lite/Full 一致.
    """

    def test_submit_top_level_takes_one_payload_arg(self) -> None:
        import inspect

        from subsystem_sdk.submit import submit

        sig = inspect.signature(submit)
        params = list(sig.parameters.values())
        assert [p.name for p in params] == ["payload"]
        assert params[0].default is inspect.Parameter.empty

    def test_lite_and_full_backend_classes_share_submit_signature(self) -> None:
        # Both PgSubmitBackend (Lite) and KafkaCompatibleSubmitBackend (Full)
        # must implement SubmitBackendInterface.submit with the same shape:
        # `(self, payload) -> Mapping | SubmitReceipt`. If a future Full
        # backend takes extra knobs, the Lite/Full parity invariant fires.
        import inspect

        from subsystem_sdk.backends.full_kafka import (
            KafkaCompatibleSubmitBackend,
        )
        from subsystem_sdk.backends.lite_pg import PgSubmitBackend

        lite_sig = inspect.signature(PgSubmitBackend.submit)
        full_sig = inspect.signature(KafkaCompatibleSubmitBackend.submit)

        # Strip self for comparison.
        def names_and_kinds(sig: inspect.Signature) -> list[tuple[str, object]]:
            return [
                (name, p.kind)
                for name, p in sig.parameters.items()
                if name != "self"
            ]

        assert names_and_kinds(lite_sig) == names_and_kinds(full_sig), (
            f"Lite/Full submit signatures diverged: "
            f"lite={names_and_kinds(lite_sig)} vs full={names_and_kinds(full_sig)}"
        )

    def test_submit_client_submit_signature_independent_of_backend(self) -> None:
        # SubmitClient.submit has the exact same shape (self, payload)
        # regardless of which backend it wraps. Iron rule: client API is
        # backend-agnostic.
        import inspect

        from subsystem_sdk.submit import SubmitClient

        sig = inspect.signature(SubmitClient.submit)
        assert [p.name for p in sig.parameters.values()] == ["self", "payload"]


# ── Red line #4: no backend-private leak in receipts ─────────────────


class TestNoBackendPrivateLeakInReceipts:
    """CLAUDE.md audit checklist #7: `SubmitReceipt` 是否暴露了 PG / Kafka
    私有字段给上层业务.
    """

    def test_reserved_private_keys_covers_pg_and_kafka_internals(self) -> None:
        from subsystem_sdk.submit import RESERVED_PRIVATE_KEYS

        # Anchor a minimum set; future backends may add more, but these
        # must not be removed silently.
        for required in (
            "pg_queue_id",
            "pg_table",
            "queue_table",
            "sql",
            "kafka_topic",
            "kafka_offset",
            "kafka_partition",
        ):
            assert required in RESERVED_PRIVATE_KEYS, (
                f"RESERVED_PRIVATE_KEYS dropped {required!r}; "
                "this is a backend-private leak guard, do not remove"
            )

    @pytest.mark.parametrize(
        "private_key",
        ["pg_queue_id", "kafka_topic", "kafka_offset"],
    )
    def test_assert_no_private_leak_rejects_each_private_key(
        self, private_key: str
    ) -> None:
        from subsystem_sdk.submit import assert_no_private_leak

        with pytest.raises(ValueError, match="backend private keys cannot leak"):
            assert_no_private_leak({private_key: "leak"})

    def test_normalize_backend_receipt_rejects_private_leak(self) -> None:
        # End-to-end: even if a backend adapter accidentally returns a
        # `kafka_offset` field, the normalizer must reject it before the
        # public SubmitReceipt is built.
        from subsystem_sdk.submit import normalize_backend_receipt

        with pytest.raises(ValueError, match="backend private keys cannot leak"):
            normalize_backend_receipt(
                {
                    "accepted": True,
                    "receipt_id": "test-id",
                    "transport_ref": None,
                    "kafka_offset": 12345,  # leak
                },
                backend_kind="full_kafka",
                validator_version="v1",
            )


# ── Red line #5: backend never receives SDK envelope (wire shape only) ──


class TestBackendNeverReceivesSdkEnvelope:
    """Stage-2.7 follow-up #2 (codex review #2 P1): the SDK envelope
    (``ex_type`` / ``semantic`` / ``produced_at``) is producer-side
    routing/derivation metadata. It MUST NOT reach the wire, otherwise:
    - Layer B's contracts.schemas.Ex* model_validate rejects the payload
      (extra='forbid').
    - PG queue rows and Kafka messages carry SDK-shape payloads instead
      of the documented contracts wire shape.

    `validate_then_dispatch` is the single place that strips the envelope
    between the SDK validator and the backend dispatch. This test exercises
    both submit-path and heartbeat-path end-to-end and asserts every
    SDK envelope field is absent from what backends record.
    """

    def test_submit_client_strips_sdk_envelope_before_backend_submit(self) -> None:
        from subsystem_sdk.backends.mock import MockSubmitBackend
        from subsystem_sdk.submit import SubmitClient
        from subsystem_sdk.validate.engine import SDK_ENVELOPE_FIELDS
        from subsystem_sdk.validate.result import ValidationResult

        backend = MockSubmitBackend()

        def permissive_validator(payload):
            # Bypass schema model_validate so we can inspect the raw
            # strip behavior independent of contracts being installed.
            return ValidationResult.ok(ex_type="Ex-2", schema_version="v-test")

        receipt = SubmitClient(backend, validator=permissive_validator).submit(
            {
                "ex_type": "Ex-2",
                "semantic": "metadata_or_heartbeat",
                "produced_at": "2026-01-01T00:00:00Z",
                "subsystem_id": "test-subsystem",
            }
        )

        assert receipt.accepted is True
        assert len(backend.submitted_payloads) == 1
        wire = backend.submitted_payloads[0]
        leaked = SDK_ENVELOPE_FIELDS.intersection(wire)
        assert not leaked, (
            f"SDK envelope leaked to submit backend: {sorted(leaked)}; "
            "validate_then_dispatch must strip envelope before dispatch"
        )
        assert wire == {"subsystem_id": "test-subsystem"}

    def test_heartbeat_client_strips_sdk_envelope_before_backend_send(self) -> None:
        from datetime import UTC, datetime

        from subsystem_sdk.backends.heartbeat import (
            SubmitBackendHeartbeatAdapter,
        )
        from subsystem_sdk.backends.mock import MockSubmitBackend
        from subsystem_sdk.heartbeat.client import HeartbeatClient
        from subsystem_sdk.heartbeat.payload import build_ex0_payload
        from subsystem_sdk.validate.engine import SDK_ENVELOPE_FIELDS
        from subsystem_sdk.validate.result import ValidationResult

        backend = MockSubmitBackend()

        def permissive_validator(payload):
            return ValidationResult.ok(ex_type="Ex-0", schema_version="v-test")

        client = HeartbeatClient(
            SubmitBackendHeartbeatAdapter(backend),
            validator=permissive_validator,
        )
        payload = build_ex0_payload(
            subsystem_id="hb-test",
            version="0.0.0",
            status="healthy",
            heartbeat_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        # The SDK-built payload DOES carry the envelope (so the SDK can
        # internally route + boundary-check it). It's the validator-then-
        # dispatch boundary that strips before the backend sees it.
        assert "ex_type" in payload and "semantic" in payload

        receipt = client.send_heartbeat(payload)
        assert receipt.accepted is True

        assert len(backend.submitted_payloads) == 1
        wire = backend.submitted_payloads[0]
        leaked = SDK_ENVELOPE_FIELDS.intersection(wire)
        assert not leaked, (
            f"SDK envelope leaked to heartbeat backend: {sorted(leaked)}; "
            "validate_then_dispatch must strip envelope before dispatch"
        )
        # Wire shape contains only producer-owned fields.
        assert wire["subsystem_id"] == "hb-test"
        assert wire["status"] == "ok"  # SDK "healthy" -> contracts wire "ok"


# ── Red line #6: public.py boundary deny scan (subprocess-isolated) ──

_BUSINESS_DOWNSTREAMS = (
    "main_core",
    "data_platform",
    "graph_engine",
    "audit_eval",
    "reasoner_runtime",
    "entity_registry",
    "subsystem_announcement",
    "subsystem_news",
    "orchestrator",
    "assembly",
    "feature_store",
    "stream_layer",
)
_HEAVY_RUNTIME_PREFIXES = (
    "psycopg",
    "pyiceberg",
    "neo4j",
    "litellm",
    "openai",
    "anthropic",
    "torch",
    "tensorflow",
    "dagster",
    "hanlp",
    "splink",
    # SDK-specific: Kafka producers must not be eagerly imported by
    # public.py either; backend adapter is constructed lazily.
    "confluent_kafka",
    "aiokafka",
    "kafka",
)
_PROBE_SCRIPT = textwrap.dedent(
    """
    import json, sys
    sys.path.insert(0, {pkg_dir!r})
    sys.path.insert(0, {contracts_src!r})
    import subsystem_sdk.public  # noqa: F401
    print(json.dumps(sorted(sys.modules.keys())))
    """
).strip()


@pytest.fixture(scope="module")
def loaded_modules_in_clean_subprocess() -> frozenset[str]:
    """Iron rule #2: subprocess-isolated import deny scan.

    Spawn a fresh Python process, import `subsystem_sdk.public`, dump
    `sys.modules` to JSON, and let the parent test only do plain JSON
    set-membership assertions. Avoids pollution from earlier tests that
    may have already imported assembly/dagster/etc.
    """

    repo_root = Path(__file__).resolve().parents[2]
    contracts_src = repo_root.parent / "contracts" / "src"
    pkg_dir = repo_root  # subsystem_sdk lives at repo root, not under src/
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE_SCRIPT.format(
                pkg_dir=str(pkg_dir),
                contracts_src=str(contracts_src),
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "subprocess probe failed; stderr:\n" + result.stderr
        )
    return frozenset(json.loads(result.stdout))


class TestPublicNoBusinessImports:
    def test_public_pulls_in_no_business_module(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod
            for mod in loaded_modules_in_clean_subprocess
            if any(mod == p or mod.startswith(p + ".") for p in _BUSINESS_DOWNSTREAMS)
        )
        assert not offenders, (
            f"subsystem_sdk.public pulled in business module(s): {offenders}; "
            "iron rule #2 violation — public boundary must stay clean"
        )

    def test_public_pulls_in_no_heavy_infra(
        self, loaded_modules_in_clean_subprocess: frozenset[str]
    ) -> None:
        offenders = sorted(
            mod
            for mod in loaded_modules_in_clean_subprocess
            if any(
                mod == p or mod.startswith(p + ".")
                for p in _HEAVY_RUNTIME_PREFIXES
            )
        )
        assert not offenders, (
            f"subsystem_sdk.public pulled in heavy infra: {offenders}; "
            "Lite/Full backend transports must be lazy — no eager Kafka/PG"
        )
