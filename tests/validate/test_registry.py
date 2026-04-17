import pytest

from subsystem_sdk._contracts import UnknownExTypeError
from subsystem_sdk.validate.registry import ValidatorRegistry


def test_registry_runs_registered_hooks() -> None:
    registry = ValidatorRegistry()
    registry.register_hook("Ex-1", lambda payload: [f"seen {payload['subsystem_id']}"])

    warnings = registry.run_hooks("Ex-1", {"subsystem_id": "subsystem-a"})

    assert warnings == ("seen subsystem-a",)


def test_registry_has_no_default_warnings() -> None:
    registry = ValidatorRegistry()

    assert registry.run_hooks("Ex-2", {"subsystem_id": "subsystem-a"}) == ()


def test_registry_rejects_unknown_ex_type() -> None:
    registry = ValidatorRegistry()

    with pytest.raises(UnknownExTypeError, match="unsupported Ex type"):
        registry.register_hook("Ex-9", lambda payload: [])

    with pytest.raises(UnknownExTypeError, match="unsupported Ex type"):
        registry.run_hooks("Ex-9", {})


def test_registry_rejects_non_callable_hooks() -> None:
    registry = ValidatorRegistry()

    with pytest.raises(TypeError, match="callable"):
        registry.register_hook("Ex-1", ["not callable"])  # type: ignore[arg-type]


def test_registry_rejects_raw_string_hook_warnings() -> None:
    registry = ValidatorRegistry()
    registry.register_hook("Ex-1", lambda payload: "abc")  # type: ignore[return-value]

    with pytest.raises(TypeError, match="sequence of warning strings"):
        registry.run_hooks("Ex-1", {})


def test_registry_rejects_non_string_hook_warning_items() -> None:
    registry = ValidatorRegistry()
    registry.register_hook("Ex-1", lambda payload: [123])  # type: ignore[list-item]

    with pytest.raises(TypeError, match="only warning strings"):
        registry.run_hooks("Ex-1", {})
