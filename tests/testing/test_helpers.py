from collections.abc import Mapping
from unittest.mock import patch

import pytest

import subsystem_sdk.testing.helpers as helpers_module
from subsystem_sdk.base import BaseSubsystemContext, SubsystemRegistrationSpec
from subsystem_sdk.fixtures import ContractExample, ContractExampleBundle
from subsystem_sdk.testing import (
    DEFAULT_SMOKE_BUNDLE_NAMES,
    MockBackend,
    build_mock_context,
    run_subsystem_smoke,
)
from subsystem_sdk.validate import ValidationResult


def _registration(
    supported_ex_types=("Ex-0", "Ex-1", "Ex-2", "Ex-3"),
) -> SubsystemRegistrationSpec:
    return SubsystemRegistrationSpec(
        subsystem_id="subsystem-reference",
        version="1.2.3",
        domain="testing",
        supported_ex_types=supported_ex_types,
        owner="sdk",
        heartbeat_policy_ref="default",
    )


def _validator(payload: Mapping[str, object]) -> ValidationResult:
    return ValidationResult.ok(
        ex_type=payload["ex_type"],  # type: ignore[arg-type]
        schema_version=f"schema-{payload['ex_type']}",
    )


def test_build_mock_context_wires_one_backend_to_both_clients() -> None:
    registration = _registration()
    backend = MockBackend()

    context = build_mock_context(
        registration,
        validator=_validator,
        backend=backend,
    )

    assert context.registration == registration
    assert context.submit_client.backend is backend
    assert context.heartbeat_client.backend is backend
    assert context.validator is _validator


def test_run_subsystem_smoke_uses_context_entrypoints() -> None:
    context = build_mock_context(_registration(), validator=_validator)
    original_submit = BaseSubsystemContext.submit
    original_send_heartbeat = BaseSubsystemContext.send_heartbeat

    with (
        patch.object(
            BaseSubsystemContext,
            "submit",
            autospec=True,
            side_effect=original_submit,
        ) as submit_spy,
        patch.object(
            BaseSubsystemContext,
            "send_heartbeat",
            autospec=True,
            side_effect=original_send_heartbeat,
        ) as heartbeat_spy,
    ):
        receipts = run_subsystem_smoke(context)

    assert len(receipts) == 4
    assert all(receipt.accepted is True for receipt in receipts)
    assert heartbeat_spy.call_count == 1
    assert submit_spy.call_count == 3


def test_run_subsystem_smoke_defaults_to_ex1_ex2_ex3_bundles() -> None:
    assert DEFAULT_SMOKE_BUNDLE_NAMES == ("ex1/default", "ex2/default", "ex3/default")

    backend = MockBackend()
    context = build_mock_context(
        _registration(),
        validator=_validator,
        backend=backend,
    )

    receipts = run_subsystem_smoke(context)

    assert len(receipts) == 4
    assert all(receipt.accepted is True for receipt in receipts)
    assert tuple(event.kind for event in backend.events) == (
        "heartbeat",
        "submit",
        "submit",
        "submit",
    )
    assert tuple(event.payload["subsystem_id"] for event in backend.events) == (
        "subsystem-reference",
        "subsystem-reference",
        "subsystem-reference",
        "subsystem-reference",
    )


def test_run_subsystem_smoke_overrides_version_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_loader(name: str) -> ContractExampleBundle:
        ex_type = {
            "ex1/default": "Ex-1",
            "ex2/default": "Ex-2",
            "ex3/default": "Ex-3",
        }[name]
        return ContractExampleBundle(
            bundle_name=name,
            ex_type=ex_type,  # type: ignore[arg-type]
            valid_examples=(
                ContractExample(
                    name=f"{name}-valid",
                    payload={
                        "ex_type": ex_type,
                        "subsystem_id": "wrong-subsystem",
                        "version": "wrong-version",
                        "produced_at": "2026-04-17T00:00:00Z",
                    },
                    notes="valid example",
                ),
            ),
            invalid_examples=(),
        )

    backend = MockBackend()
    context = build_mock_context(
        _registration(),
        validator=_validator,
        backend=backend,
    )
    monkeypatch.setattr(helpers_module, "load_fixture_bundle", fake_loader)

    run_subsystem_smoke(context)

    for event in backend.events[1:]:
        assert event.payload["subsystem_id"] == "subsystem-reference"
        assert event.payload["version"] == "1.2.3"
        assert "submitted_at" not in event.payload
        assert "ingest_seq" not in event.payload
        assert "layer_b_receipt_id" not in event.payload


def test_run_subsystem_smoke_requires_all_main_ex_types_without_backend_call() -> None:
    backend = MockBackend()
    context = build_mock_context(
        _registration(supported_ex_types=("Ex-0", "Ex-1", "Ex-2")),
        validator=_validator,
        backend=backend,
    )

    with pytest.raises(ValueError, match="missing: Ex-3"):
        run_subsystem_smoke(context)

    assert backend.events == ()
