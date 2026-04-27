from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from subsystem_sdk.validate import (
    EntityPreflightResult,
    EntityRegistryLookup,
    PreflightPolicy,
    run_entity_preflight,
)


class FakeLookup:
    def __init__(self, known_refs: Iterable[str] = ()) -> None:
        self._known_refs = set(known_refs)
        self.calls: list[tuple[str, ...]] = []

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        self.calls.append(refs_tuple)
        return {ref: ref in self._known_refs for ref in refs_tuple}


class MissingRefLookup:
    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        return {"known-entity": True}


class MalformedLookup:
    def lookup(self, refs: Iterable[str]) -> Mapping[str, object]:
        return {ref: "false" for ref in refs}


class RaisingLookup:
    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        raise RuntimeError("registry unavailable")


class Ex1PayloadModel(BaseModel):
    """Test data class for ``run_entity_preflight`` (NOT a contracts
    schema). The SDK preflight uses ``produced_at`` as a marker to
    recognize Ex-1/2/3 shape (see semantics._PRODUCED_SCHEMA_MARKERS),
    so this test model keeps it. ``validate_payload`` strips it before
    contracts model_validate — that strip path is exercised in
    test_engine.py / test_report.py / test_contracts_alignment.py, NOT
    here. ``ex_type`` is kept defaulted so the routing identifier is
    explicit.
    """

    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    produced_at: str
    entity_ref: str


def _produced_payload(ex_type: str = "Ex-1") -> dict[str, Any]:
    return {
        "ex_type": ex_type,
        "subsystem_id": "subsystem-demo",
        "produced_at": "2026-04-18T00:00:00Z",
    }


def _heartbeat_payload() -> dict[str, Any]:
    return {
        "ex_type": "Ex-0",
        "subsystem_id": "subsystem-demo",
        "version": "1.0.0",
        "heartbeat_at": "2026-04-18T00:00:00Z",
        "status": "ok",
    }


def test_preflight_result_is_immutable_extra_forbidden_and_tuple_normalized() -> None:
    result = EntityPreflightResult(
        checked=True,
        unresolved_refs=["missing-entity"],
        warnings=["entity preflight warning"],
        policy="warn",
    )

    assert result.unresolved_refs == ("missing-entity",)
    assert result.warnings == ("entity preflight warning",)

    with pytest.raises(ValidationError, match="frozen"):
        result.checked = False  # type: ignore[misc]

    with pytest.raises(ValidationError, match="Extra inputs"):
        EntityPreflightResult(
            checked=True,
            policy="warn",
            unexpected=True,
        )


def test_preflight_result_json_safe_dump_helper() -> None:
    result = EntityPreflightResult(
        checked=True,
        unresolved_refs=("missing-entity",),
        warnings=("entity preflight warning",),
        policy="block",
    )

    dumped = result.to_validation_preflight()

    assert dumped == {
        "checked": True,
        "unresolved_refs": ["missing-entity"],
        "warnings": ["entity preflight warning"],
        "policy": "block",
    }
    assert result.model_dump(mode="json") == {
        "checked": True,
        "unresolved_refs": ["missing-entity"],
        "warnings": ["entity preflight warning"],
        "policy": "block",
    }
    json.dumps(dumped)


def test_run_entity_preflight_warns_for_unresolved_refs_without_blocking() -> None:
    lookup = FakeLookup(known_refs={"known-entity"})
    payload = _produced_payload() | {
        "entity_ref": "known-entity",
        "canonical_entity_id": "missing-entity",
    }

    result = run_entity_preflight(payload, lookup=lookup, policy="warn")

    assert result.checked is True
    assert result.unresolved_refs == ("missing-entity",)
    assert result.warnings
    assert result.policy == "warn"
    assert result.has_unresolved_refs is True
    assert result.should_block is False
    assert lookup.calls == [("known-entity", "missing-entity")]


def test_run_entity_preflight_block_policy_sets_should_block_only() -> None:
    payload = _produced_payload() | {"entity_ref": "missing-entity"}

    result = run_entity_preflight(payload, lookup=FakeLookup(), policy="block")

    assert result.checked is True
    assert result.unresolved_refs == ("missing-entity",)
    assert result.should_block is True
    assert not hasattr(result, "errors")


def test_run_entity_preflight_skip_policy_does_not_call_lookup() -> None:
    lookup = FakeLookup()
    payload = _produced_payload() | {"entity_ref": "missing-entity"}

    result = run_entity_preflight(payload, lookup=lookup, policy="skip")

    assert result.checked is False
    assert result.policy == "skip"
    assert result.unresolved_refs == ()
    assert any("skipped by policy" in warning for warning in result.warnings)
    assert lookup.calls == []


def test_run_entity_preflight_without_lookup_degrades_to_skip() -> None:
    payload = _produced_payload() | {"entity_ref": "missing-entity"}

    result = run_entity_preflight(payload)

    assert result.checked is False
    assert result.policy == "skip"
    assert result.unresolved_refs == ()
    assert any("no lookup channel" in warning for warning in result.warnings)


def test_run_entity_preflight_lookup_exception_degrades_to_skip() -> None:
    payload = _produced_payload() | {"entity_ref": "missing-entity"}

    result = run_entity_preflight(payload, lookup=RaisingLookup())

    assert result.checked is False
    assert result.policy == "skip"
    assert result.unresolved_refs == ()
    assert any("registry unavailable" in warning for warning in result.warnings)


def test_run_entity_preflight_missing_lookup_result_is_unresolved() -> None:
    payload = _produced_payload() | {
        "entity_ref": "known-entity",
        "target_entity_id": "missing-entity",
    }

    result = run_entity_preflight(payload, lookup=MissingRefLookup())

    assert result.checked is True
    assert result.unresolved_refs == ("missing-entity",)
    assert result.warnings


def test_run_entity_preflight_non_bool_lookup_result_is_unresolved_in_block_mode() -> None:
    payload = _produced_payload() | {"entity_ref": "missing-entity"}

    result = run_entity_preflight(payload, lookup=MalformedLookup(), policy="block")

    assert result.checked is True
    assert result.unresolved_refs == ("missing-entity",)
    assert result.should_block is True
    assert any("non-bool" in warning for warning in result.warnings)
    assert any("unresolved" in warning for warning in result.warnings)


def test_run_entity_preflight_extracts_refs_in_first_seen_order_only() -> None:
    lookup = FakeLookup(
        known_refs={
            "entity-a",
            "entity-b",
            "entity-c",
            "entity-d",
            "entity-e",
            "entity-f",
            "entity-g",
            "entity-h",
            "entity-i",
        }
    )
    payload = _produced_payload("Ex-2") | {
        "canonical_entity_id": "entity-a",
        "affected_entities": ["entity-f", "entity-g"],
        "title": "not-an-entity-ref",
        "items": [
            {"entity_ref": "entity-b"},
            {"notes": "entity-should-not-be-scanned"},
            {"entity_refs": ["entity-a", "entity-c"]},
        ],
        "relationship": {
            "source_entity_id": "entity-d",
            "target_entity_id": "entity-e",
            "source_node": "entity-h",
            "target_node": "entity-i",
            "body": "entity-should-also-not-be-scanned",
        },
    }

    result = run_entity_preflight(payload, lookup=lookup)

    assert result.checked is True
    assert result.unresolved_refs == ()
    assert lookup.calls == [
        (
            "entity-a",
            "entity-f",
            "entity-g",
            "entity-b",
            "entity-c",
            "entity-d",
            "entity-e",
            "entity-h",
            "entity-i",
        )
    ]


def test_run_entity_preflight_blocks_ex2_affected_entities() -> None:
    payload = _produced_payload("Ex-2") | {
        "affected_entities": ["known-entity", "missing-entity"],
    }

    result = run_entity_preflight(
        payload,
        lookup=FakeLookup(known_refs={"known-entity"}),
        policy="block",
    )

    assert result.checked is True
    assert result.unresolved_refs == ("missing-entity",)
    assert result.should_block is True


def test_run_entity_preflight_blocks_ex3_endpoint_nodes() -> None:
    payload = _produced_payload("Ex-3") | {
        "source_node": "known-source",
        "target_node": "missing-target",
    }

    result = run_entity_preflight(
        payload,
        lookup=FakeLookup(known_refs={"known-source"}),
        policy="block",
    )

    assert result.checked is True
    assert result.unresolved_refs == ("missing-target",)
    assert result.should_block is True


def test_run_entity_preflight_skips_ex0_without_lookup_or_entity_ref_scan() -> None:
    lookup = FakeLookup()
    payload = _heartbeat_payload() | {"entity_id": "should-not-be-checked"}

    result = run_entity_preflight(payload, lookup=lookup, policy="block")

    assert result.checked is False
    assert result.policy == "skip"
    assert result.should_block is False
    assert any("Ex-0" in warning for warning in result.warnings)
    assert lookup.calls == []


def test_run_entity_preflight_skips_unrecognized_payload() -> None:
    lookup = FakeLookup()
    payload = {
        "subsystem_id": "subsystem-demo",
        "produced_at": "2026-04-18T00:00:00Z",
        "entity_ref": "missing-entity",
    }

    result = run_entity_preflight(payload, lookup=lookup)

    assert result.checked is False
    assert result.policy == "skip"
    assert any("not a recognized" in warning for warning in result.warnings)
    assert lookup.calls == []


def test_run_entity_preflight_accepts_pydantic_base_model_payload() -> None:
    lookup = FakeLookup(known_refs={"known-entity"})
    payload = Ex1PayloadModel(
        subsystem_id="subsystem-demo",
        produced_at="2026-04-18T00:00:00Z",
        entity_ref="known-entity",
    )

    result = run_entity_preflight(payload, lookup=lookup)

    assert result.checked is True
    assert result.unresolved_refs == ()
    assert lookup.calls == [("known-entity",)]


def test_run_entity_preflight_does_not_modify_payload_or_generate_ids() -> None:
    payload = _produced_payload("Ex-3") | {
        "entity_ref": "missing-entity",
        "notes": ["missing-entity"],
    }
    before = copy.deepcopy(payload)

    result = run_entity_preflight(payload, lookup=FakeLookup(), policy="block")

    assert result.should_block is True
    assert payload == before
    assert "canonical_entity_id" not in payload
    assert "submitted_at" not in payload
    assert "ingest_seq" not in payload
    assert "layer_b_receipt_id" not in payload


def test_validate_package_exports_preflight_types() -> None:
    assert EntityPreflightResult.__name__ == "EntityPreflightResult"
    assert hasattr(EntityRegistryLookup, "lookup")
    assert PreflightPolicy
    assert callable(run_entity_preflight)


def test_preflight_module_does_not_import_contracts_directly() -> None:
    source = Path("subsystem_sdk/validate/preflight.py").read_text()

    assert "import contracts" not in source
    assert "from contracts" not in source
