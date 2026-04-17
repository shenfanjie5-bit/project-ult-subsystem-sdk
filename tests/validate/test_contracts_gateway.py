import sys
import types
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk._contracts import (
    ContractsSchemaError,
    ContractsUnavailableError,
    UnknownExTypeError,
    get_ex_schema,
    get_schema_version,
)


class FakeEx1Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1"

    ex_type: str


def _install_contracts(
    monkeypatch: pytest.MonkeyPatch, module: types.ModuleType
) -> None:
    monkeypatch.setitem(sys.modules, "contracts", module)


def test_get_ex_schema_loads_model_from_contracts_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {"Ex-1": FakeEx1Payload}
    _install_contracts(monkeypatch, module)

    assert get_ex_schema("Ex-1") is FakeEx1Payload


def test_get_ex_schema_loads_model_from_contracts_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("contracts")
    module.Ex1Payload = FakeEx1Payload
    _install_contracts(monkeypatch, module)

    assert get_ex_schema("Ex-1") is FakeEx1Payload


def test_get_ex_schema_rejects_unknown_ex_type() -> None:
    with pytest.raises(UnknownExTypeError, match="unsupported Ex type"):
        get_ex_schema("Ex-9")


def test_get_ex_schema_reports_missing_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "contracts", raising=False)
    original_import = __import__("importlib").import_module

    def _missing_contracts(name: str) -> types.ModuleType:
        if name == "contracts":
            raise ModuleNotFoundError("No module named 'contracts'")
        return original_import(name)

    monkeypatch.setattr(
        "subsystem_sdk._contracts.importlib.import_module", _missing_contracts
    )

    with pytest.raises(
        ContractsUnavailableError, match="contracts package is not available"
    ):
        get_ex_schema("Ex-1")


def test_get_ex_schema_reports_missing_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {}
    _install_contracts(monkeypatch, module)

    with pytest.raises(ContractsSchemaError, match="could not be resolved"):
        get_ex_schema("Ex-1")


def test_get_ex_schema_rejects_non_pydantic_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {"Ex-1": object}
    _install_contracts(monkeypatch, module)

    with pytest.raises(ContractsSchemaError, match="model_validate"):
        get_ex_schema("Ex-1")


def test_get_schema_version_reads_class_attributes() -> None:
    assert get_schema_version(FakeEx1Payload) == "v-ex1"


def test_get_schema_version_reads_model_config() -> None:
    class ConfigVersionPayload(BaseModel):
        model_config = ConfigDict(schema_version="v-config")

    assert get_schema_version(ConfigVersionPayload) == "v-config"


def test_get_schema_version_uses_unknown_when_absent() -> None:
    class UnversionedPayload(BaseModel):
        pass

    assert get_schema_version(UnversionedPayload) == "unknown"
