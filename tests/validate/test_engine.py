import inspect
import sys
import types
from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk import _contracts
from subsystem_sdk.validate import registry
from subsystem_sdk.validate.engine import validate_payload


"""Test-only fake contract schemas.

Stage-2.7 P1 follow-up: these mirror the real ``contracts.schemas.Ex*``
shape (extra='forbid', NO ``ex_type`` / ``semantic`` / ``produced_at``
fields — those are SDK envelope, stripped by
``validate_payload._strip_sdk_envelope`` before ``schema.model_validate``).
If the fakes regrow envelope fields, they stop mirroring real contracts
and start hiding bugs (which is exactly what codex stage-2.7 P2 flagged).
"""


class Ex0Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex0"
    model_config = ConfigDict(extra="forbid")

    subsystem_id: str
    version: str
    heartbeat_at: str
    status: str


class Ex1Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1"
    model_config = ConfigDict(extra="forbid")

    subsystem_id: str


class Ex2Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex2"
    model_config = ConfigDict(extra="forbid")

    subsystem_id: str


class Ex3Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex3"
    model_config = ConfigDict(extra="forbid")

    subsystem_id: str


def _schemas() -> dict[str, type[BaseModel]]:
    return {
        "Ex-0": Ex0Payload,
        "Ex-1": Ex1Payload,
        "Ex-2": Ex2Payload,
        "Ex-3": Ex3Payload,
    }


def _install_contracts(
    monkeypatch: pytest.MonkeyPatch, schemas: dict[str, type[BaseModel]] | None = None
) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = schemas if schemas is not None else _schemas()
    monkeypatch.setitem(sys.modules, "contracts", module)


def _payload(ex_type: str) -> dict[str, object]:
    if ex_type == "Ex-0":
        return {
            "ex_type": "Ex-0",
            "subsystem_id": "subsystem-a",
            "version": "1.0.0",
            "heartbeat_at": "2026-04-17T00:00:00Z",
            "status": "ok",
        }

    return {
        "ex_type": ex_type,
        "subsystem_id": "subsystem-a",
        "produced_at": "2026-04-17T00:00:00Z",
    }


@pytest.fixture(autouse=True)
def _reset_default_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_DEFAULT_REGISTRY", registry.ValidatorRegistry())


def test_validate_payload_signature_has_no_ex_type_parameter() -> None:
    assert "ex_type" not in inspect.signature(validate_payload).parameters


@pytest.mark.parametrize("ex_type", ("Ex-0", "Ex-1", "Ex-2", "Ex-3"))
def test_validate_payload_accepts_supported_ex_payloads(
    monkeypatch: pytest.MonkeyPatch, ex_type: str
) -> None:
    _install_contracts(monkeypatch)

    result = validate_payload(_payload(ex_type))

    assert result.is_valid is True
    assert result.ex_type == ex_type
    assert result.schema_version == f"v-ex{ex_type[-1]}"
    assert result.field_errors == ()


def test_validate_payload_returns_schema_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_contracts(monkeypatch)

    # Stage-2.7 P1 follow-up: ``produced_at`` is now SDK envelope and is
    # stripped by validate_payload before schema.model_validate, so we
    # can't trigger a contracts-level schema error via that field.
    # ``subsystem_id`` IS a real producer-owned field that contracts
    # validates, so set it to a list to force a Pydantic type error.
    result = validate_payload(_payload("Ex-1") | {"subsystem_id": ["not", "a", "str"]})

    assert result.is_valid is False
    assert result.ex_type == "Ex-1"
    assert result.schema_version == "v-ex1"
    assert any("subsystem_id" in error for error in result.field_errors)


def test_validate_payload_returns_contracts_unavailable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "contracts", raising=False)

    def _missing_contracts(name: str) -> types.ModuleType:
        if name == "contracts":
            raise ModuleNotFoundError("No module named 'contracts'")
        return _contracts.importlib.import_module(name)

    monkeypatch.setattr(_contracts.importlib, "import_module", _missing_contracts)

    result = validate_payload(_payload("Ex-1"))

    assert result.is_valid is False
    assert result.ex_type == "Ex-1"
    assert any(
        "contracts package is not available" in error
        for error in result.field_errors
    )


def test_validate_payload_rejects_unknown_ex_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_contracts(monkeypatch)

    result = validate_payload(_payload("Ex-1") | {"ex_type": "Ex-9"})

    assert result.is_valid is False
    assert any("unsupported Ex type" in error for error in result.field_errors)


def test_validate_payload_merges_registry_hook_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_contracts(monkeypatch)
    registry.register_hook("Ex-2", lambda payload: ["weak producer warning"])

    result = validate_payload(_payload("Ex-2"))

    assert result.is_valid is True
    assert result.warnings == ("weak producer warning",)


def test_validate_payload_rejects_ex0_business_semantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_contracts(monkeypatch)

    result = validate_payload(_payload("Ex-0") | {"business_event": "trade"})

    assert result.is_valid is False
    assert result.ex_type == "Ex-0"
    assert any("non-heartbeat" in error for error in result.field_errors)


def test_validate_payload_rejects_schema_metadata_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MismatchedEx1Payload(Ex1Payload):
        ex_type: Literal["Ex-2"] = "Ex-2"

    schemas = _schemas() | {"Ex-1": MismatchedEx1Payload}
    _install_contracts(monkeypatch, schemas)

    result = validate_payload(_payload("Ex-1"))

    assert result.is_valid is False
    assert result.ex_type == "Ex-1"
    assert any("schema metadata" in error for error in result.field_errors)


def test_validate_payload_calls_producer_guard_before_contracts_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _guard(payload: object) -> None:
        calls.append("producer_guard")

    def _get_schema(ex_type: str) -> type[BaseModel]:
        assert calls == ["producer_guard"]
        calls.append("contracts")
        return Ex1Payload

    monkeypatch.setattr(
        "subsystem_sdk.validate.engine.semantics.assert_producer_only", _guard
    )
    monkeypatch.setattr("subsystem_sdk.validate.engine.get_ex_schema", _get_schema)

    result = validate_payload(_payload("Ex-1"))

    assert result.is_valid is True
    assert calls == ["producer_guard", "contracts"]


def test_validate_payload_non_mapping_returns_failure() -> None:
    result = validate_payload(["not", "a", "payload"])  # type: ignore[arg-type]

    assert result.is_valid is False
    assert result.field_errors == ("payload must be a mapping or Pydantic BaseModel",)
