import pytest

from subsystem_sdk.validate import (
    EX0_BANNED_SEMANTICS,
    EX0_SEMANTIC,
    Ex0SemanticError,
    SemanticsError,
    assert_ex0_semantic,
)


def test_ex0_semantic_constant_is_metadata_or_heartbeat() -> None:
    assert EX0_SEMANTIC == "metadata_or_heartbeat"


def test_assert_ex0_semantic_accepts_metadata_or_heartbeat() -> None:
    assert_ex0_semantic(EX0_SEMANTIC)


@pytest.mark.parametrize("declared_semantic", sorted(EX0_BANNED_SEMANTICS))
def test_assert_ex0_semantic_rejects_banned_semantics(
    declared_semantic: str,
) -> None:
    with pytest.raises(Ex0SemanticError, match=declared_semantic):
        assert_ex0_semantic(declared_semantic)


def test_ex0_semantic_error_inherits_from_value_error() -> None:
    assert issubclass(Ex0SemanticError, SemanticsError)
    assert issubclass(Ex0SemanticError, ValueError)
