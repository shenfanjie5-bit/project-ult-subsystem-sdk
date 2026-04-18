from __future__ import annotations

import json
import sys
import types
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.backends import (
    KafkaBrokerAck,
    SubmitBackendConfig,
    SubmitBackendHeartbeatAdapter,
    build_submit_backend,
)
from subsystem_sdk.base import (
    BaseSubsystemContext,
    SubsystemRegistrationSpec,
    load_submit_backend_config,
)
from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.submit import SubmitClient, SubmitReceipt
from subsystem_sdk.validate import ValidationResult, registry, validate_payload

_PUBLIC_RECEIPT_KEYS = {
    "accepted",
    "receipt_id",
    "backend_kind",
    "transport_ref",
    "validator_version",
    "warnings",
    "errors",
}
_PRIVATE_TRANSPORT_KEYS = {
    "pg_queue_id",
    "queue_table",
    "sql",
    "kafka_topic",
    "kafka_partition",
    "kafka_offset",
    "topic",
    "partition",
    "offset",
}


class Ex0Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex0-switch"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-0"] = "Ex-0"
    semantic: Literal["metadata_or_heartbeat"] = "metadata_or_heartbeat"
    subsystem_id: str
    version: str
    heartbeat_at: str
    status: str


class Ex1Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1-switch"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    produced_at: datetime
    canonical_entity_id: str | None = None


class Ex2Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex2-switch"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-2"] = "Ex-2"
    subsystem_id: str
    produced_at: datetime
    canonical_entity_id: str | None = None


class Ex3Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex3-switch"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-3"] = "Ex-3"
    subsystem_id: str
    produced_at: datetime
    canonical_entity_id: str | None = None


class FakePgRecorder:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.sql: list[str] = []
        self.next_id = 0

    def connect(self, config: SubmitBackendConfig) -> "FakePgConnection":
        return FakePgConnection(self)


class FakePgConnection:
    def __init__(self, recorder: FakePgRecorder) -> None:
        self._recorder = recorder
        self.commits = 0
        self.closed = False

    def cursor(self) -> "FakePgCursor":
        return FakePgCursor(self._recorder)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


class FakePgCursor:
    def __init__(self, recorder: FakePgRecorder) -> None:
        self._recorder = recorder
        self._row: tuple[int] | None = None

    def __enter__(self) -> "FakePgCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[str]) -> None:
        self._recorder.next_id += 1
        self._recorder.sql.append(sql)
        self._recorder.payloads.append(json.loads(params[0]))
        self._row = (self._recorder.next_id,)

    def fetchone(self) -> tuple[int]:
        assert self._row is not None
        return self._row


class FakeKafkaProducer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str | None]] = []

    def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str | None = None,
    ) -> KafkaBrokerAck:
        self.calls.append((topic, payload, key))
        return KafkaBrokerAck(message_id=f"message-{len(self.calls)}", offset=3)


class InvalidAckKafkaProducer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str | None]] = []

    def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str | None = None,
    ) -> object:
        self.calls.append((topic, payload, key))
        return object()


class RecordingLookup:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        self.calls.append(refs_tuple)
        return {ref: False for ref in refs_tuple}


class RejectingBackend:
    def __init__(self, backend_kind: Literal["lite_pg", "full_kafka"]) -> None:
        self.backend_kind = backend_kind
        self.calls: list[Mapping[str, Any]] = []

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(payload)
        return {
            "accepted": False,
            "transport_ref": None,
            "warnings": ("backend warning",),
            "errors": ("backend rejected",),
        }


@dataclass
class BackendRun:
    config: SubmitBackendConfig
    backend_factory: Callable[[SubmitBackendConfig], Any]
    calls: Callable[[], int]


@pytest.fixture(autouse=True)
def _fake_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    contracts = types.ModuleType("contracts")
    contracts.EX_PAYLOAD_SCHEMAS = {
        "Ex-0": Ex0Payload,
        "Ex-1": Ex1Payload,
        "Ex-2": Ex2Payload,
        "Ex-3": Ex3Payload,
    }
    monkeypatch.setitem(sys.modules, "contracts", contracts)
    monkeypatch.setattr(registry, "_DEFAULT_REGISTRY", registry.ValidatorRegistry())


def _valid_ex2_payload() -> dict[str, str]:
    return {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-switch",
        "produced_at": "2026-04-18T00:00:00Z",
    }


def _registration() -> SubsystemRegistrationSpec:
    return SubsystemRegistrationSpec(
        subsystem_id="subsystem-switch",
        version="1.0.0",
        domain="switch",
        supported_ex_types=("Ex-0", "Ex-1", "Ex-2", "Ex-3"),
        owner="sdk",
        heartbeat_policy_ref="default",
    )


def _backend_run(backend_kind: Literal["lite_pg", "full_kafka"]) -> BackendRun:
    if backend_kind == "lite_pg":
        recorder = FakePgRecorder()
        config = SubmitBackendConfig(
            backend_kind="lite_pg",
            queue_table="submit_queue",
        )

        def factory(received: SubmitBackendConfig) -> Any:
            return build_submit_backend(
                received,
                pg_connection_factory=recorder.connect,
            )

        return BackendRun(config, factory, lambda: len(recorder.payloads))

    producer = FakeKafkaProducer()
    config = SubmitBackendConfig(
        backend_kind="full_kafka",
        topic="candidate-events",
    )

    def factory(received: SubmitBackendConfig) -> Any:
        return build_submit_backend(received, kafka_producer=producer)

    return BackendRun(config, factory, lambda: len(producer.calls))


def _submit_with_config(
    backend_kind: Literal["lite_pg", "full_kafka"],
    payload: Mapping[str, Any],
    *,
    validator: Callable[[Mapping[str, Any]], ValidationResult] = validate_payload,
    entity_lookup: RecordingLookup | None = None,
    preflight_policy: Literal["skip", "warn", "block"] = "skip",
) -> tuple[SubmitReceipt, BackendRun]:
    run = _backend_run(backend_kind)
    client = SubmitClient.from_config(
        run.config,
        backend_factory=run.backend_factory,
        validator=validator,
        entity_lookup=entity_lookup,
        preflight_policy=preflight_policy,
    )
    return client.submit(payload), run


def _assert_public_receipt(receipt: SubmitReceipt) -> None:
    dumped = receipt.model_dump()
    assert set(dumped) == _PUBLIC_RECEIPT_KEYS
    assert _PRIVATE_TRANSPORT_KEYS.isdisjoint(dumped)


def test_same_valid_payload_keeps_receipt_contract_across_lite_and_full() -> None:
    payload = _valid_ex2_payload()

    lite_receipt, lite_run = _submit_with_config("lite_pg", payload)
    full_receipt, full_run = _submit_with_config("full_kafka", payload)

    _assert_public_receipt(lite_receipt)
    _assert_public_receipt(full_receipt)
    assert lite_receipt.backend_kind == "lite_pg"
    assert full_receipt.backend_kind == "full_kafka"
    assert lite_receipt.accepted == full_receipt.accepted is True
    assert lite_receipt.errors == full_receipt.errors == ()
    assert lite_receipt.warnings == full_receipt.warnings == ()
    assert lite_receipt.validator_version == full_receipt.validator_version
    assert lite_receipt.validator_version == "v-ex2-switch"
    assert lite_receipt.transport_ref != full_receipt.transport_ref
    assert lite_run.calls() == 1
    assert full_run.calls() == 1


def test_same_invalid_payload_fails_before_lite_or_full_backend_call() -> None:
    payload = _valid_ex2_payload()
    del payload["produced_at"]

    lite_receipt, lite_run = _submit_with_config("lite_pg", payload)
    full_receipt, full_run = _submit_with_config("full_kafka", payload)

    assert lite_receipt.accepted == full_receipt.accepted is False
    assert lite_receipt.transport_ref is None
    assert full_receipt.transport_ref is None
    assert lite_receipt.errors == full_receipt.errors
    assert lite_receipt.warnings == full_receipt.warnings
    assert lite_receipt.validator_version == full_receipt.validator_version
    assert lite_run.calls() == 0
    assert full_run.calls() == 0


def test_full_backend_from_config_returns_receipt_on_serialization_failure() -> None:
    producer = FakeKafkaProducer()
    config = SubmitBackendConfig(
        backend_kind="full_kafka",
        topic="candidate-events",
    )
    payload = _valid_ex2_payload() | {
        "produced_at": datetime(2026, 4, 18, tzinfo=timezone.utc)
    }

    def factory(received: SubmitBackendConfig) -> Any:
        return build_submit_backend(received, kafka_producer=producer)

    receipt = SubmitClient.from_config(config, backend_factory=factory).submit(payload)

    assert producer.calls == []
    assert receipt.accepted is False
    assert receipt.backend_kind == "full_kafka"
    assert receipt.transport_ref is None
    assert receipt.validator_version == "v-ex2-switch"
    assert receipt.errors == (
        "full_kafka submit failed: Object of type datetime is not JSON serializable",
    )


def test_full_backend_from_config_keeps_successful_send_accepted_on_invalid_ack() -> None:
    producer = InvalidAckKafkaProducer()
    config = SubmitBackendConfig(
        backend_kind="full_kafka",
        topic="candidate-events",
    )
    payload = _valid_ex2_payload()

    def factory(received: SubmitBackendConfig) -> Any:
        return build_submit_backend(received, kafka_producer=producer)

    receipt = SubmitClient.from_config(config, backend_factory=factory).submit(payload)

    assert producer.calls == [
        (
            "candidate-events",
            b'{"ex_type":"Ex-2","produced_at":"2026-04-18T00:00:00Z","subsystem_id":"subsystem-switch"}',
            None,
        )
    ]
    assert receipt.accepted is True
    assert receipt.backend_kind == "full_kafka"
    assert receipt.transport_ref is not None
    assert receipt.transport_ref.startswith("kafka:unverified:")
    assert receipt.validator_version == "v-ex2-switch"
    assert receipt.warnings == (
        "full_kafka ack normalization failed after send: "
        "Kafka producer ack must be KafkaBrokerAck or a mapping",
    )
    assert receipt.errors == ()


def test_full_backend_config_file_builds_client_through_documented_factory_path(
    tmp_path,
) -> None:
    config_path = tmp_path / "full-backend.toml"
    config_path.write_text(
        """
[backend]
backend_kind = "full_kafka"
topic = "candidate-events"
client_id = "subsystem-switch"
""",
        encoding="utf-8",
    )
    producer = FakeKafkaProducer()
    config = load_submit_backend_config(config_path)

    def factory(received: SubmitBackendConfig) -> Any:
        assert received is config
        return build_submit_backend(received, kafka_producer=producer)

    receipt = SubmitClient.from_config(config, backend_factory=factory).submit(
        _valid_ex2_payload()
    )

    assert receipt.accepted is True
    assert receipt.backend_kind == "full_kafka"
    assert producer.calls


def test_base_context_submit_uses_same_caller_for_lite_and_full() -> None:
    payload = _valid_ex2_payload()

    def business_submit(context: BaseSubsystemContext) -> SubmitReceipt:
        return context.submit(payload)

    for backend_kind in ("lite_pg", "full_kafka"):
        run = _backend_run(backend_kind)
        submit_client = SubmitClient.from_config(
            run.config,
            backend_factory=run.backend_factory,
        )
        context = BaseSubsystemContext(
            registration=_registration(),
            submit_client=submit_client,
            heartbeat_client=HeartbeatClient(
                SubmitBackendHeartbeatAdapter(submit_client.backend),
            ),
            validator=validate_payload,
        )

        receipt = business_submit(context)

        assert receipt.accepted is True
        assert receipt.backend_kind == backend_kind
        assert run.calls() == 1


def test_config_built_client_keeps_already_preflighted_warning_idempotent() -> None:
    payload = _valid_ex2_payload() | {"canonical_entity_id": "missing-entity"}
    lookup = RecordingLookup()

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        assert received is payload
        return ValidationResult.ok(
            ex_type="Ex-2",
            schema_version="custom-preflight-v1",
            warnings=("preflight warning",),
            preflight={
                "checked": True,
                "unresolved_refs": ["missing-entity"],
                "warnings": ["preflight warning"],
                "policy": "warn",
            },
        )

    lite_receipt, lite_run = _submit_with_config(
        "lite_pg",
        payload,
        validator=validator,
        entity_lookup=lookup,
        preflight_policy="warn",
    )
    full_receipt, full_run = _submit_with_config(
        "full_kafka",
        payload,
        validator=validator,
        entity_lookup=lookup,
        preflight_policy="warn",
    )

    assert lookup.calls == []
    assert lite_run.calls() == 1
    assert full_run.calls() == 1
    assert lite_receipt.accepted == full_receipt.accepted is True
    assert lite_receipt.warnings == full_receipt.warnings == ("preflight warning",)
    assert lite_receipt.validator_version == full_receipt.validator_version


def test_config_built_block_preflighted_invalid_result_skips_both_backends() -> None:
    payload = _valid_ex2_payload() | {"canonical_entity_id": "missing-entity"}
    lookup = RecordingLookup()

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        assert received is payload
        return ValidationResult.fail(
            ex_type="Ex-2",
            schema_version="custom-preflight-v1",
            field_errors=("entity preflight blocked unresolved reference(s): missing",),
            warnings=("preflight warning",),
            preflight={
                "checked": True,
                "unresolved_refs": ["missing"],
                "warnings": ["preflight warning"],
                "policy": "block",
            },
        )

    lite_receipt, lite_run = _submit_with_config(
        "lite_pg",
        payload,
        validator=validator,
        entity_lookup=lookup,
        preflight_policy="block",
    )
    full_receipt, full_run = _submit_with_config(
        "full_kafka",
        payload,
        validator=validator,
        entity_lookup=lookup,
        preflight_policy="block",
    )

    assert lookup.calls == []
    assert lite_run.calls() == 0
    assert full_run.calls() == 0
    assert lite_receipt.accepted == full_receipt.accepted is False
    assert lite_receipt.errors == full_receipt.errors
    assert lite_receipt.warnings == full_receipt.warnings
    assert lite_receipt.validator_version == full_receipt.validator_version


@pytest.mark.parametrize("backend_kind", ("lite_pg", "full_kafka"))
def test_config_built_client_preserves_backend_rejection_warning_order(
    backend_kind: Literal["lite_pg", "full_kafka"],
) -> None:
    config = (
        SubmitBackendConfig(backend_kind="lite_pg")
        if backend_kind == "lite_pg"
        else SubmitBackendConfig(backend_kind="full_kafka", topic="candidate-events")
    )
    backend = RejectingBackend(backend_kind)

    def backend_factory(received: SubmitBackendConfig) -> RejectingBackend:
        assert received is config
        return backend

    def validator(payload: Mapping[str, Any]) -> ValidationResult:
        return ValidationResult.ok(
            ex_type="Ex-2",
            schema_version="validator-v1",
            warnings=("validator warning",),
        )

    receipt = SubmitClient.from_config(
        config,
        backend_factory=backend_factory,
        validator=validator,
    ).submit(_valid_ex2_payload())

    assert backend.calls == [_valid_ex2_payload()]
    assert receipt.accepted is False
    assert receipt.errors == ("backend rejected",)
    assert receipt.warnings == ("validator warning", "backend warning")
