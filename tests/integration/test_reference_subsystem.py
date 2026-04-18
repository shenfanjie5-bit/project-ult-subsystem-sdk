import importlib
import json
import sys
import types
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

import subsystem_sdk.testing.helpers as helpers_module
from subsystem_sdk.backends.config import SubmitBackendConfig
from subsystem_sdk.backends.lite_pg import PgSubmitBackend
from subsystem_sdk.base import (
    BaseSubsystem,
    BaseSubsystemContext,
    SubsystemRegistrationSpec,
)
from subsystem_sdk.base.scaffold import create_reference_subsystem
from subsystem_sdk.fixtures import ContractExample, ContractExampleBundle
from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.testing import MockBackend, run_subsystem_smoke
from subsystem_sdk.submit import SubmitClient
from subsystem_sdk.validate import validate_payload


class FakeEx0Schema(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex0-reference"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-0"] = "Ex-0"
    semantic: Literal["metadata_or_heartbeat"] = "metadata_or_heartbeat"
    subsystem_id: str
    version: str
    heartbeat_at: str
    status: str
    last_output_at: str | None = None
    pending_count: int | None = None


class FakeEx1Schema(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1-reference"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    produced_at: str
    canonical_entity_id: str | None = None


class FakeEx2Schema(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex2-reference"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-2"] = "Ex-2"
    subsystem_id: str
    produced_at: str


class FakeEx3Schema(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex3-reference"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-3"] = "Ex-3"
    subsystem_id: str
    produced_at: str


class FakePgRecorder:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.sql: list[str] = []
        self.next_id = 0

    def connect(self, config: SubmitBackendConfig) -> "FakePgConnection":
        return FakePgConnection(self)


class FakePgConnection:
    def __init__(self, recorder: FakePgRecorder) -> None:
        self._recorder = recorder
        self.committed = False
        self.closed = False

    def cursor(self) -> "FakePgCursor":
        return FakePgCursor(self._recorder)

    def commit(self) -> None:
        self.committed = True

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


class MissingEntityLookup:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        self.calls.append(refs_tuple)
        return {ref: False for ref in refs_tuple}


def _install_fake_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {
        "Ex-0": FakeEx0Schema,
        "Ex-1": FakeEx1Schema,
        "Ex-2": FakeEx2Schema,
        "Ex-3": FakeEx3Schema,
    }
    monkeypatch.setitem(sys.modules, "contracts", module)


def _registration() -> SubsystemRegistrationSpec:
    return SubsystemRegistrationSpec(
        subsystem_id="subsystem-reference",
        version="0.1.0",
        domain="reference",
        supported_ex_types=["Ex-0", "Ex-1", "Ex-2", "Ex-3"],
        owner="sdk",
        heartbeat_policy_ref="default",
    )


def _import_generated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    package_name: str,
):
    create_reference_subsystem(_registration(), tmp_path, package_name=package_name)
    monkeypatch.syspath_prepend(str(tmp_path))
    return importlib.import_module(package_name)


def _ex1_unresolved_bundle(name: str) -> ContractExampleBundle:
    return ContractExampleBundle(
        bundle_name=name,
        ex_type="Ex-1",
        valid_examples=(
            ContractExample(
                name="unresolved-entity-ref",
                payload={
                    "ex_type": "Ex-1",
                    "subsystem_id": "subsystem-placeholder",
                    "produced_at": "2026-04-18T00:00:00Z",
                    "canonical_entity_id": "missing-entity",
                },
                notes="Valid contract payload with an unresolved entity ref.",
            ),
        ),
        invalid_examples=(),
    )


def test_generated_reference_subsystem_smoke_with_mock_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_contracts(monkeypatch)
    generated = _import_generated(monkeypatch, tmp_path, "reference_e2e_mock")
    backend = MockBackend()
    context = generated.build_context(backend)

    receipts = run_subsystem_smoke(context)

    assert len(receipts) == 4
    assert all(receipt.accepted is True for receipt in receipts)
    assert tuple(receipt.validator_version for receipt in receipts) == (
        "v-ex0-reference",
        "v-ex1-reference",
        "v-ex2-reference",
        "v-ex3-reference",
    )
    assert tuple(event.kind for event in backend.events) == (
        "heartbeat",
        "submit",
        "submit",
        "submit",
    )


def test_generated_reference_subsystem_switches_to_lite_without_smoke_api_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_contracts(monkeypatch)
    generated = _import_generated(monkeypatch, tmp_path, "reference_e2e_lite")
    recorder = FakePgRecorder()
    lite_backend = PgSubmitBackend(
        SubmitBackendConfig(backend_kind="lite_pg", queue_table="submit_queue"),
        connection_factory=recorder.connect,
    )
    context = generated.build_context(lite_backend)

    receipts = run_subsystem_smoke(context)

    assert len(receipts) == 4
    assert all(receipt.accepted is True for receipt in receipts)
    assert {receipt.backend_kind for receipt in receipts} == {"lite_pg"}
    assert [payload["ex_type"] for payload in recorder.payloads] == [
        "Ex-0",
        "Ex-1",
        "Ex-2",
        "Ex-3",
    ]
    assert all(
        payload["subsystem_id"] == "subsystem-reference"
        for payload in recorder.payloads
    )


def test_generated_reference_context_works_with_base_subsystem_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_contracts(monkeypatch)
    generated = _import_generated(monkeypatch, tmp_path, "reference_e2e_wrapper")
    backend = MockBackend()
    subsystem = BaseSubsystem(generated.build_context(backend))

    receipt = subsystem.submit(
        {
            "ex_type": "Ex-2",
            "subsystem_id": "subsystem-reference",
            "produced_at": "2026-04-17T00:00:00Z",
        }
    )

    assert receipt.accepted is True
    assert receipt.validator_version == "v-ex2-reference"


def test_reference_smoke_records_unresolved_ex1_preflight_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_contracts(monkeypatch)
    generated = _import_generated(monkeypatch, tmp_path, "reference_e2e_preflight")
    backend = MockBackend()
    lookup = MissingEntityLookup()
    registration = generated.load_registration()
    real_loader = helpers_module.load_fixture_bundle
    context = BaseSubsystemContext(
        registration=registration,
        submit_client=SubmitClient(
            backend,
            entity_lookup=lookup,
            preflight_policy="warn",
        ),
        heartbeat_client=HeartbeatClient(backend),
        validator=validate_payload,
    )

    def fake_loader(name: str) -> ContractExampleBundle:
        if name == "ex1/default":
            return _ex1_unresolved_bundle(name)
        return real_loader(name)

    monkeypatch.setattr(helpers_module, "load_fixture_bundle", fake_loader)

    receipts = run_subsystem_smoke(context, bundle_names=("ex1/default",))

    assert len(receipts) == 2
    assert receipts[1].accepted is True
    assert receipts[1].errors == ()
    assert receipts[1].warnings == (
        "entity preflight found unresolved reference(s): missing-entity",
    )
    assert lookup.calls == [("missing-entity",)]
    assert tuple(event.kind for event in backend.events) == ("heartbeat", "submit")
