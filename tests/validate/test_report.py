from __future__ import annotations

import json
import sys
import types
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.validate import registry
from subsystem_sdk.validate.engine import validate_payload
from subsystem_sdk.validate.report import richer_validation_report
from subsystem_sdk.validate.result import ValidationResult


class Ex0Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex0-report"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-0"] = "Ex-0"
    semantic: Literal["metadata_or_heartbeat"] = "metadata_or_heartbeat"
    subsystem_id: str
    version: str
    heartbeat_at: str
    status: str


class Ex1Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1-report"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    produced_at: str
    canonical_entity_id: str | None = None


class Ex2Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex2-report"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-2"] = "Ex-2"
    subsystem_id: str
    produced_at: str


class Ex3Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex3-report"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-3"] = "Ex-3"
    subsystem_id: str
    produced_at: str


class RecordingLookup:
    def __init__(self, resolved_refs: Iterable[str] = ()) -> None:
        self._resolved_refs = set(resolved_refs)
        self.calls: list[tuple[str, ...]] = []

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        self.calls.append(refs_tuple)
        return {ref: ref in self._resolved_refs for ref in refs_tuple}


def _install_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {
        "Ex-0": Ex0Payload,
        "Ex-1": Ex1Payload,
        "Ex-2": Ex2Payload,
        "Ex-3": Ex3Payload,
    }
    monkeypatch.setitem(sys.modules, "contracts", module)


def _payload(ex_type: str = "Ex-1", **extra: Any) -> dict[str, Any]:
    if ex_type == "Ex-0":
        return {
            "ex_type": "Ex-0",
            "semantic": "metadata_or_heartbeat",
            "subsystem_id": "subsystem-report",
            "version": "1.0.0",
            "heartbeat_at": "2026-04-18T00:00:00Z",
            "status": "ok",
        } | extra

    return {
        "ex_type": ex_type,
        "subsystem_id": "subsystem-report",
        "produced_at": "2026-04-18T00:00:00Z",
    } | extra


@pytest.fixture(autouse=True)
def _fake_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_contracts(monkeypatch)
    monkeypatch.setattr(registry, "_DEFAULT_REGISTRY", registry.ValidatorRegistry())


def test_report_for_valid_result_has_stable_empty_sections() -> None:
    result = validate_payload(_payload("Ex-2"))

    report = richer_validation_report(result)

    assert report == richer_validation_report(result)
    assert report == "\n".join(
        [
            "Validation Report",
            "ex_type: Ex-2",
            "schema_version: v-ex2-report",
            "status: valid",
            "field_errors:",
            "  - none",
            "warnings:",
            "  - none",
            "preflight:",
            "  checked: false",
            "  policy: none",
            "  unresolved_refs:",
            "    - none",
            "  warnings:",
            "    - none",
        ]
    )


def test_report_for_invalid_result_includes_field_errors_only() -> None:
    result = validate_payload(_payload("Ex-1", produced_at=["not", "a", "string"]))

    report = richer_validation_report(result)

    assert "status: invalid" in report
    assert "field_errors:" in report
    assert "produced_at" in report
    assert "warnings:\n  - none" in report
    assert "preflight:\n  checked: false" in report


def test_warn_preflight_enriches_validation_result_and_report() -> None:
    lookup = RecordingLookup()
    result = validate_payload(
        _payload("Ex-1", canonical_entity_id="missing-entity"),
        entity_lookup=lookup,
        preflight_policy="warn",
    )

    report = richer_validation_report(result)

    assert result.is_valid is True
    assert result.field_errors == ()
    assert result.preflight == {
        "checked": True,
        "unresolved_refs": ("missing-entity",),
        "warnings": (
            "entity preflight found unresolved reference(s): missing-entity",
        ),
        "policy": "warn",
    }
    assert result.warnings == (
        "entity preflight found unresolved reference(s): missing-entity",
    )
    assert lookup.calls == [("missing-entity",)]
    assert "status: valid" in report
    assert "policy: warn" in report
    assert "missing-entity" in report
    assert report == richer_validation_report(result)


def test_block_preflight_returns_invalid_result_with_serializable_preflight() -> None:
    result = validate_payload(
        _payload("Ex-1", canonical_entity_id="missing-entity"),
        entity_lookup=RecordingLookup(),
        preflight_policy="block",
    )

    report = richer_validation_report(result)

    assert result.is_valid is False
    assert result.field_errors == (
        "entity preflight blocked unresolved reference(s): missing-entity",
    )
    assert result.warnings == (
        "entity preflight found unresolved reference(s): missing-entity",
    )
    assert result.preflight is not None
    assert result.model_dump(mode="json")["preflight"] == {
        "checked": True,
        "unresolved_refs": ["missing-entity"],
        "warnings": [
            "entity preflight found unresolved reference(s): missing-entity"
        ],
        "policy": "block",
    }
    json.dumps(result.model_dump(mode="json")["preflight"])
    assert "status: invalid" in report
    assert "policy: block" in report
    assert "missing-entity" in report


def test_validate_payload_default_skip_leaves_preflight_empty() -> None:
    lookup = RecordingLookup()

    result = validate_payload(
        _payload("Ex-1", canonical_entity_id="missing-entity"),
        entity_lookup=lookup,
    )

    assert result.is_valid is True
    assert result.preflight is None
    assert result.warnings == ()
    assert lookup.calls == []


def test_validate_payload_does_not_preflight_invalid_payloads() -> None:
    lookup = RecordingLookup()

    result = validate_payload(
        _payload("Ex-1", produced_at=["bad"], canonical_entity_id="missing-entity"),
        entity_lookup=lookup,
        preflight_policy="warn",
    )

    assert result.is_valid is False
    assert result.preflight is None
    assert lookup.calls == []


def test_validate_payload_does_not_preflight_ex0_payloads() -> None:
    lookup = RecordingLookup()

    result = validate_payload(
        _payload("Ex-0"),
        entity_lookup=lookup,
        preflight_policy="block",
    )

    assert result.is_valid is True
    assert result.preflight is None
    assert lookup.calls == []


def test_report_handles_manual_warning_only_preflight_result() -> None:
    result = ValidationResult.ok(
        ex_type="Ex-3",
        schema_version="manual-v1",
        warnings=("manual warning",),
        preflight={
            "checked": True,
            "policy": "warn",
            "unresolved_refs": [],
            "warnings": ["manual preflight warning"],
        },
    )

    report = richer_validation_report(result)

    assert "status: valid" in report
    assert "manual warning" in report
    assert "policy: warn" in report
    assert "manual preflight warning" in report
