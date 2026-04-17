import sys
import types
from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.fixtures import available_fixture_bundles, load_fixture_bundle
from subsystem_sdk.validate import registry
from subsystem_sdk.validate.engine import validate_payload


class FakeEx0Schema(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex0-fixture"
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
    SCHEMA_VERSION: ClassVar[str] = "v-ex1-fixture"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    produced_at: str


class FakeEx2Schema(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex2-fixture"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-2"] = "Ex-2"
    subsystem_id: str
    produced_at: str


class FakeEx3Schema(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex3-fixture"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-3"] = "Ex-3"
    subsystem_id: str
    produced_at: str


def _install_fake_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {
        "Ex-0": FakeEx0Schema,
        "Ex-1": FakeEx1Schema,
        "Ex-2": FakeEx2Schema,
        "Ex-3": FakeEx3Schema,
    }
    monkeypatch.setitem(sys.modules, "contracts", module)


@pytest.fixture(autouse=True)
def _fake_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_contracts(monkeypatch)
    monkeypatch.setattr(registry, "_DEFAULT_REGISTRY", registry.ValidatorRegistry())


@pytest.mark.parametrize("bundle_name", available_fixture_bundles())
def test_valid_examples_roundtrip_through_real_validator(bundle_name: str) -> None:
    bundle = load_fixture_bundle(bundle_name)

    for example in bundle.valid_examples:
        result = validate_payload(example.payload)

        assert result.is_valid is True, (bundle_name, example.name, result)
        assert result.ex_type == bundle.ex_type
        assert result.field_errors == ()


@pytest.mark.parametrize("bundle_name", available_fixture_bundles())
def test_invalid_examples_fail_through_real_validator(bundle_name: str) -> None:
    bundle = load_fixture_bundle(bundle_name)

    for example in bundle.invalid_examples:
        result = validate_payload(example.payload)

        assert result.is_valid is False, (bundle_name, example.name)
        assert result.field_errors, (bundle_name, example.name)


def _invalid_result(bundle_name: str, example_name: str) -> tuple[str, ...]:
    bundle = load_fixture_bundle(bundle_name)
    for example in bundle.invalid_examples:
        if example.name == example_name:
            result = validate_payload(example.payload)
            assert result.is_valid is False
            return result.field_errors
    raise AssertionError(f"missing fixture example {bundle_name}:{example_name}")


def test_regression_ex0_rejects_non_heartbeat_semantic() -> None:
    errors = _invalid_result("ex0/default", "business-event-semantic")

    assert any("metadata_or_heartbeat" in error for error in errors)


@pytest.mark.parametrize(
    ("bundle_name", "example_name", "field_name"),
    (
        ("ex0/default", "ingest-submitted-at-leak", "submitted_at"),
        ("ex2/default", "ingest-seq-leak", "ingest_seq"),
        ("ex3/default", "layer-b-receipt-id-leak", "layer_b_receipt_id"),
    ),
)
def test_regression_rejects_ingest_metadata_leaks(
    bundle_name: str, example_name: str, field_name: str
) -> None:
    errors = _invalid_result(bundle_name, example_name)

    assert any(field_name in error for error in errors)


def test_regression_rejects_missing_ex_type() -> None:
    errors = _invalid_result("ex1/default", "missing-ex-type")

    assert any("ex_type" in error for error in errors)


def test_regression_rejects_unsupported_ex_type() -> None:
    errors = _invalid_result("ex1/default", "unknown-ex-type")

    assert any("unsupported Ex type" in error for error in errors)
