import dataclasses

import pytest

from subsystem_sdk.heartbeat import DEFAULT_HEARTBEAT_POLICY, HeartbeatPolicy


def test_default_heartbeat_policy_matches_section_19_target() -> None:
    assert DEFAULT_HEARTBEAT_POLICY.interval_seconds > 0
    assert DEFAULT_HEARTBEAT_POLICY.timeout_ms == 300


def test_heartbeat_policy_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_HEARTBEAT_POLICY.timeout_ms = 100  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    (
        ("interval_seconds", {"interval_seconds": 0}),
        ("interval_seconds", {"interval_seconds": -1}),
        ("timeout_ms", {"timeout_ms": 0}),
        ("timeout_ms", {"timeout_ms": -1}),
    ),
)
def test_heartbeat_policy_requires_positive_values(
    field_name: str, kwargs: dict[str, int]
) -> None:
    with pytest.raises(ValueError, match=field_name):
        HeartbeatPolicy(**kwargs)


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    (
        ("interval_seconds", {"interval_seconds": True}),
        ("timeout_ms", {"timeout_ms": "300"}),
    ),
)
def test_heartbeat_policy_requires_integer_values(
    field_name: str, kwargs: dict[str, object]
) -> None:
    with pytest.raises(TypeError, match=field_name):
        HeartbeatPolicy(**kwargs)  # type: ignore[arg-type]
