from __future__ import annotations

import sys
import types
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.submit import SubmitClient
from subsystem_sdk.validate import ValidationResult, registry
from subsystem_sdk.validate.engine import strip_sdk_envelope


def _wire(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return what ``validate_then_dispatch`` will hand to the backend
    (SDK envelope stripped). Stage-2.7 follow-up #2: backends MUST receive
    wire shape, not the original SDK-enveloped payload.
    """

    return dict(strip_sdk_envelope(payload))


class Ex0Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex0-submit"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-0"] = "Ex-0"
    subsystem_id: str
    version: str
    heartbeat_at: str
    status: str


class Ex1Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1-submit"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    canonical_entity_id: str | None = None


class Ex2Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex2-submit"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-2"] = "Ex-2"
    subsystem_id: str
    affected_entities: list[str] = []


class Ex3Payload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex3-submit"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-3"] = "Ex-3"
    subsystem_id: str
    source_node: str | None = None
    target_node: str | None = None


class RecordingLookup:
    def __init__(self, resolved_refs: Iterable[str] = ()) -> None:
        self._resolved_refs = set(resolved_refs)
        self.calls: list[tuple[str, ...]] = []

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        self.calls.append(refs_tuple)
        return {ref: ref in self._resolved_refs for ref in refs_tuple}


class RaisingLookup:
    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        raise RuntimeError("live registry unavailable")


class RecordingBackend:
    backend_kind = "mock"

    def __init__(
        self,
        *,
        accepted: bool = True,
        warnings: tuple[str, ...] = ("backend warning",),
        errors: tuple[str, ...] = (),
    ) -> None:
        self._accepted = accepted
        self._warnings = warnings
        self._errors = errors
        self.calls: list[Mapping[str, Any]] = []

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(payload)
        return {
            "accepted": self._accepted,
            "receipt_id": "backend-receipt-1",
            "transport_ref": "backend-transport-1",
            "warnings": self._warnings,
            "errors": self._errors,
        }


def _install_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {
        "Ex-0": Ex0Payload,
        "Ex-1": Ex1Payload,
        "Ex-2": Ex2Payload,
        "Ex-3": Ex3Payload,
    }
    monkeypatch.setitem(sys.modules, "contracts", module)


def _payload(**extra: Any) -> dict[str, Any]:
    return {
        "ex_type": "Ex-1",
        "subsystem_id": "subsystem-submit",
        "produced_at": "2026-04-18T00:00:00Z",
    } | extra


@pytest.fixture(autouse=True)
def _fake_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_contracts(monkeypatch)
    monkeypatch.setattr(registry, "_DEFAULT_REGISTRY", registry.ValidatorRegistry())


def test_submit_client_warn_preflight_accepts_and_merges_warnings() -> None:
    backend = RecordingBackend()
    lookup = RecordingLookup()
    payload = _payload(canonical_entity_id="missing-entity")

    receipt = SubmitClient(
        backend,
        entity_lookup=lookup,
        preflight_policy="warn",
    ).submit(payload)

    assert backend.calls == [_wire(payload)]
    assert lookup.calls == [("missing-entity",)]
    assert receipt.accepted is True
    assert receipt.errors == ()
    assert receipt.warnings == (
        "entity preflight found unresolved reference(s): missing-entity",
        "backend warning",
    )


def test_submit_client_block_preflight_rejects_without_backend_call() -> None:
    backend = RecordingBackend()

    receipt = SubmitClient(
        backend,
        entity_lookup=RecordingLookup(),
        preflight_policy="block",
    ).submit(_payload(canonical_entity_id="missing-entity"))

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.errors == (
        "entity preflight blocked unresolved reference(s): missing-entity",
    )
    assert receipt.warnings == (
        "entity preflight found unresolved reference(s): missing-entity",
    )
    assert receipt.backend_kind == "mock"
    assert receipt.validator_version == "v-ex1-submit"


def test_submit_client_block_preflight_rejects_unresolved_ex2_entities_without_backend_call() -> None:
    backend = RecordingBackend()
    payload = {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-submit",
        "produced_at": "2026-04-18T00:00:00Z",
        "affected_entities": ["missing-entity"],
    }

    receipt = SubmitClient(
        backend,
        entity_lookup=RecordingLookup(),
        preflight_policy="block",
    ).submit(payload)

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.errors == (
        "entity preflight blocked unresolved reference(s): missing-entity",
    )
    assert receipt.validator_version == "v-ex2-submit"


def test_submit_client_block_preflight_rejects_unresolved_ex3_endpoint_nodes_without_backend_call() -> None:
    backend = RecordingBackend()
    payload = {
        "ex_type": "Ex-3",
        "subsystem_id": "subsystem-submit",
        "produced_at": "2026-04-18T00:00:00Z",
        "source_node": "known-source",
        "target_node": "missing-target",
    }

    receipt = SubmitClient(
        backend,
        entity_lookup=RecordingLookup(resolved_refs={"known-source"}),
        preflight_policy="block",
    ).submit(payload)

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.errors == (
        "entity preflight blocked unresolved reference(s): missing-target",
    )
    assert receipt.validator_version == "v-ex3-submit"


def test_submit_client_backend_rejection_preserves_warning_merge_order() -> None:
    backend = RecordingBackend(
        accepted=False,
        warnings=("backend warning",),
        errors=("backend rejected",),
    )

    receipt = SubmitClient(
        backend,
        entity_lookup=RecordingLookup(),
        preflight_policy="warn",
    ).submit(_payload(canonical_entity_id="missing-entity"))

    assert receipt.accepted is False
    assert receipt.errors == ("backend rejected",)
    assert receipt.warnings == (
        "entity preflight found unresolved reference(s): missing-entity",
        "backend warning",
    )


def test_submit_client_custom_validator_still_receives_only_payload() -> None:
    backend = RecordingBackend()
    lookup = RecordingLookup()
    calls: list[tuple[tuple[Mapping[str, Any], ...], dict[str, Any]]] = []

    def validator(*args: Mapping[str, Any], **kwargs: Any) -> ValidationResult:
        calls.append((args, kwargs))
        return ValidationResult.ok(
            ex_type="Ex-1",
            schema_version="custom-validator-v1",
            warnings=("validator warning",),
        )

    payload = _payload(canonical_entity_id="missing-entity")
    receipt = SubmitClient(
        backend,
        validator=validator,
        entity_lookup=lookup,
        preflight_policy="warn",
    ).submit(payload)

    assert calls == [((payload,), {})]
    assert backend.calls == [_wire(payload)]
    assert receipt.validator_version == "custom-validator-v1"
    assert receipt.warnings == (
        "validator warning",
        "entity preflight found unresolved reference(s): missing-entity",
        "backend warning",
    )


def test_submit_client_default_does_not_run_preflight_lookup() -> None:
    backend = RecordingBackend()
    lookup = RecordingLookup()
    payload = _payload(canonical_entity_id="missing-entity")

    receipt = SubmitClient(backend, entity_lookup=lookup).submit(payload)

    assert receipt.accepted is True
    assert receipt.warnings == ("backend warning",)
    assert lookup.calls == []


def test_submit_client_production_profile_fails_closed_when_live_lookup_unavailable() -> None:
    backend = RecordingBackend()

    receipt = SubmitClient(
        backend,
        entity_lookup=RaisingLookup(),
        entity_preflight_profile="production",
    ).submit(_payload(canonical_entity_id="ENT_STOCK_600519.SH"))

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.errors == (
        "entity preflight blocked: lookup channel failed: live registry unavailable",
    )
    assert receipt.warnings == (
        "entity preflight failed closed: lookup channel failed: live registry unavailable",
    )


def test_submit_client_dev_profile_allows_lookup_unavailable_warning() -> None:
    backend = RecordingBackend()

    receipt = SubmitClient(
        backend,
        entity_lookup=RaisingLookup(),
        preflight_policy="warn",
        entity_preflight_profile="dev",
    ).submit(_payload(canonical_entity_id="ENT_STOCK_600519.SH"))

    assert backend.calls
    assert receipt.accepted is True
    assert receipt.warnings == (
        "entity preflight skipped: lookup channel failed: live registry unavailable",
        "backend warning",
    )


def test_submit_client_production_profile_blocks_unresolved_ex2_refs() -> None:
    backend = RecordingBackend()
    payload = {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-submit",
        "produced_at": "2026-04-18T00:00:00Z",
        "affected_entities": ["ENT_STOCK_600519.SH", "ENT_STOCK_MISSING.SZ"],
    }

    receipt = SubmitClient(
        backend,
        entity_lookup=RecordingLookup(resolved_refs={"ENT_STOCK_600519.SH"}),
        entity_preflight_profile="production",
    ).submit(payload)

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.errors == (
        "entity preflight blocked unresolved reference(s): ENT_STOCK_MISSING.SZ",
    )


def test_submit_client_production_profile_blocks_unresolved_ex3_refs() -> None:
    backend = RecordingBackend()
    payload = {
        "ex_type": "Ex-3",
        "subsystem_id": "subsystem-submit",
        "produced_at": "2026-04-18T00:00:00Z",
        "source_node": "ENT_STOCK_600519.SH",
        "target_node": "ENT_STOCK_MISSING.SZ",
    }

    receipt = SubmitClient(
        backend,
        entity_lookup=RecordingLookup(resolved_refs={"ENT_STOCK_600519.SH"}),
        entity_preflight_profile="production",
    ).submit(payload)

    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.errors == (
        "entity preflight blocked unresolved reference(s): ENT_STOCK_MISSING.SZ",
    )


def test_submit_client_already_preflighted_warn_result_is_idempotent() -> None:
    backend = RecordingBackend(warnings=())
    lookup = RecordingLookup()
    payload = _payload(canonical_entity_id="missing-entity")

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        assert received is payload
        return ValidationResult.ok(
            ex_type="Ex-1",
            schema_version="preflighted-v1",
            warnings=("existing preflight warning",),
            preflight={
                "checked": True,
                "unresolved_refs": ["missing-entity"],
                "warnings": ["existing preflight warning"],
                "policy": "warn",
            },
        )

    receipt = SubmitClient(
        backend,
        validator=validator,
        entity_lookup=lookup,
        preflight_policy="warn",
    ).submit(payload)

    assert lookup.calls == []
    assert backend.calls == [_wire(payload)]
    assert receipt.accepted is True
    assert receipt.warnings == ("existing preflight warning",)


def test_submit_client_already_preflighted_block_result_is_idempotent() -> None:
    backend = RecordingBackend()
    lookup = RecordingLookup()
    payload = _payload(canonical_entity_id="missing-entity")

    def validator(received: Mapping[str, Any]) -> ValidationResult:
        assert received is payload
        return ValidationResult.fail(
            ex_type="Ex-1",
            schema_version="preflighted-v2",
            field_errors=("entity preflight blocked unresolved reference(s): missing",),
            warnings=("existing preflight warning",),
            preflight={
                "checked": True,
                "unresolved_refs": ["missing"],
                "warnings": ["existing preflight warning"],
                "policy": "block",
            },
        )

    receipt = SubmitClient(
        backend,
        validator=validator,
        entity_lookup=lookup,
        preflight_policy="block",
    ).submit(payload)

    assert lookup.calls == []
    assert backend.calls == []
    assert receipt.accepted is False
    assert receipt.warnings == ("existing preflight warning",)
    assert receipt.errors == (
        "entity preflight blocked unresolved reference(s): missing",
    )
