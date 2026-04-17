import pytest

from subsystem_sdk.validate import (
    EX0_BANNED_SEMANTICS,
    EX0_SEMANTIC,
    Ex0SemanticError,
    assert_ex0_semantic,
)


def test_ex0_semantic_accepts_metadata_or_heartbeat() -> None:
    assert_ex0_semantic(EX0_SEMANTIC)


@pytest.mark.parametrize("declared_semantic", sorted(EX0_BANNED_SEMANTICS))
def test_ex0_banned_semantics_raise(declared_semantic: str) -> None:
    with pytest.raises(Ex0SemanticError, match=declared_semantic):
        assert_ex0_semantic(declared_semantic)
