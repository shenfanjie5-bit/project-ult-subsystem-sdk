import pytest
from pydantic import ValidationError

from subsystem_sdk.base.registration import (
    RegistrationError,
    RegistrationRegistry,
    SubsystemRegistrationSpec,
    get_registered_subsystem,
    register_subsystem,
)


def _spec(**overrides: object) -> SubsystemRegistrationSpec:
    data: dict[str, object] = {
        "subsystem_id": "subsystem-demo",
        "version": "0.1.0",
        "domain": "demo",
        "supported_ex_types": ["Ex-1", "Ex-2"],
        "owner": "sdk",
        "heartbeat_policy_ref": "default",
    }
    data.update(overrides)
    return SubsystemRegistrationSpec.model_validate(data)


def test_registration_spec_accepts_section_9_fields() -> None:
    spec = _spec()

    assert spec.subsystem_id == "subsystem-demo"
    assert spec.version == "0.1.0"
    assert spec.domain == "demo"
    assert spec.supported_ex_types == ("Ex-1", "Ex-2")
    assert spec.owner == "sdk"
    assert spec.heartbeat_policy_ref == "default"
    assert spec.capabilities == {}


def test_registration_spec_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _spec(queue_table="private_queue")


def test_supported_ex_types_are_normalized_to_tuple() -> None:
    spec = _spec(supported_ex_types=["Ex-0", "Ex-1"])

    assert spec.supported_ex_types == ("Ex-0", "Ex-1")


def test_supported_ex_types_reject_unknown_values() -> None:
    with pytest.raises(ValidationError, match="unsupported Ex type"):
        _spec(supported_ex_types=["Ex-1", "Ex-9"])


@pytest.mark.parametrize(
    "field_name",
    ("subsystem_id", "version", "domain", "owner", "heartbeat_policy_ref"),
)
def test_string_fields_must_be_non_empty(field_name: str) -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        _spec(**{field_name: "  "})


def test_registration_spec_is_frozen() -> None:
    spec = _spec()

    with pytest.raises(ValidationError):
        spec.version = "0.2.0"  # type: ignore[misc]


def test_capabilities_do_not_keep_callers_mutable_dict_reference() -> None:
    capabilities = {"mode": "local", "nested": {"enabled": True}, "flags": ["a"]}
    spec = _spec(capabilities=capabilities)

    capabilities["mode"] = "mutated"
    capabilities["nested"]["enabled"] = False  # type: ignore[index]
    capabilities["flags"].append("b")  # type: ignore[attr-defined]

    assert spec.capabilities == {
        "mode": "local",
        "nested": {"enabled": True},
        "flags": ("a",),
    }


def test_capabilities_are_exposed_as_immutable_metadata() -> None:
    spec = _spec(capabilities={"nested": {"enabled": True}})

    with pytest.raises(TypeError):
        spec.capabilities["new"] = "value"  # type: ignore[index]

    with pytest.raises(TypeError):
        spec.capabilities["nested"]["enabled"] = False  # type: ignore[index]


def test_capabilities_dump_as_plain_containers() -> None:
    spec = _spec(capabilities={"flags": ["a"], "nested": {"enabled": True}})

    assert spec.model_dump()["capabilities"] == {
        "flags": ["a"],
        "nested": {"enabled": True},
    }


def test_registry_register_and_get() -> None:
    registry = RegistrationRegistry()
    spec = _spec()

    registry.register(spec)

    assert registry.get("subsystem-demo") == spec
    assert registry.get("missing") is None


def test_registry_duplicate_identical_spec_is_idempotent() -> None:
    registry = RegistrationRegistry()
    spec = _spec()

    registry.register(spec)
    registry.register(_spec())

    assert registry.get("subsystem-demo") == spec


@pytest.mark.parametrize(
    "field_name,value",
    (
        ("version", "0.2.0"),
        ("domain", "other"),
        ("owner", "other-owner"),
    ),
)
def test_registry_duplicate_identity_conflict_raises(
    field_name: str,
    value: str,
) -> None:
    registry = RegistrationRegistry()
    registry.register(_spec())

    with pytest.raises(RegistrationError, match="subsystem-demo"):
        registry.register(_spec(**{field_name: value}))


def test_registry_clear_is_available_for_tests() -> None:
    registry = RegistrationRegistry()
    registry.register(_spec())

    registry.clear()

    assert registry.get("subsystem-demo") is None


def test_module_registration_api_uses_provided_registry() -> None:
    registry = RegistrationRegistry()
    spec = _spec()

    register_subsystem(spec, registry=registry)

    assert get_registered_subsystem("subsystem-demo", registry=registry) == spec
