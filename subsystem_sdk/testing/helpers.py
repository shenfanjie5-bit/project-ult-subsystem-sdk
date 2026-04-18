"""High-level testing helpers for reference subsystem smoke runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from subsystem_sdk._json import copy_json_like
from subsystem_sdk.base import BaseSubsystemContext, SubsystemRegistrationSpec
from subsystem_sdk.fixtures import load_fixture_bundle
from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.submit import SubmitClient, SubmitReceipt
from subsystem_sdk.testing.mock_backend import MockBackend
from subsystem_sdk.validate import ValidationResult, validate_payload
from subsystem_sdk.validate.semantics import assert_no_ingest_metadata

DEFAULT_SMOKE_BUNDLE_NAMES: Final[tuple[str, ...]] = (
    "ex1/default",
    "ex2/default",
    "ex3/default",
)
_REQUIRED_SMOKE_EX_TYPES: Final[tuple[str, ...]] = ("Ex-0", "Ex-1", "Ex-2", "Ex-3")


def _require_smoke_support(registration: SubsystemRegistrationSpec) -> None:
    supported = set(registration.supported_ex_types)
    missing = [
        ex_type for ex_type in _REQUIRED_SMOKE_EX_TYPES if ex_type not in supported
    ]
    if missing:
        required = ", ".join(_REQUIRED_SMOKE_EX_TYPES)
        missing_text = ", ".join(missing)
        raise ValueError(
            "registration "
            f"{registration.subsystem_id!r} must support smoke Ex type(s): "
            f"{required}; missing: {missing_text}"
        )


def _smoke_payload(
    payload: Mapping[str, Any],
    registration: SubsystemRegistrationSpec,
) -> dict[str, Any]:
    copied = copy_json_like(payload)
    if not isinstance(copied, dict):
        raise TypeError("fixture valid example payload must be a mapping")
    copied["subsystem_id"] = registration.subsystem_id
    if "version" in copied:
        copied["version"] = registration.version
    assert_no_ingest_metadata(copied)
    return copied


def build_mock_context(
    spec: SubsystemRegistrationSpec,
    *,
    validator: Callable[[Mapping[str, Any]], ValidationResult] = validate_payload,
    backend: MockBackend | None = None,
) -> BaseSubsystemContext:
    """Build a context whose submit and heartbeat clients share one mock backend."""

    mock_backend = backend or MockBackend()
    return BaseSubsystemContext(
        registration=spec,
        submit_client=SubmitClient(mock_backend, validator=validator),
        heartbeat_client=HeartbeatClient(mock_backend, validator=validator),
        validator=validator,
    )


def run_subsystem_smoke(
    context: BaseSubsystemContext,
    *,
    bundle_names: Sequence[str] = DEFAULT_SMOKE_BUNDLE_NAMES,
) -> tuple[SubmitReceipt, ...]:
    """Run heartbeat plus Ex-1/2/3 fixture submissions through a context."""

    _require_smoke_support(context.registration)
    receipts: list[SubmitReceipt] = [
        context.send_heartbeat({"status": "healthy"}),
    ]

    for bundle_name in bundle_names:
        bundle = load_fixture_bundle(bundle_name)
        if not bundle.valid_examples:
            raise ValueError(f"fixture bundle has no valid examples: {bundle_name!r}")
        payload = _smoke_payload(
            bundle.valid_examples[0].payload,
            context.registration,
        )
        receipts.append(context.submit(payload))

    return tuple(receipts)
