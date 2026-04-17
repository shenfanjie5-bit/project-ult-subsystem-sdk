import pytest

from subsystem_sdk.fixtures import (
    ContractExampleBundle,
    FixtureLoadError,
    available_fixture_bundles,
    load_fixture_bundle,
)


EXPECTED_BUNDLE_NAMES = ("ex0/default", "ex1/default", "ex2/default", "ex3/default")
EXPECTED_EX_TYPES = {
    "ex0/default": "Ex-0",
    "ex1/default": "Ex-1",
    "ex2/default": "Ex-2",
    "ex3/default": "Ex-3",
}


def test_available_fixture_bundles_lists_builtin_defaults() -> None:
    assert available_fixture_bundles() == EXPECTED_BUNDLE_NAMES


@pytest.mark.parametrize("bundle_name", EXPECTED_BUNDLE_NAMES)
def test_load_fixture_bundle_returns_contract_bundle(bundle_name: str) -> None:
    bundle = load_fixture_bundle(bundle_name)

    assert isinstance(bundle, ContractExampleBundle)
    assert bundle.bundle_name == bundle_name
    assert bundle.ex_type == EXPECTED_EX_TYPES[bundle_name]


def test_load_fixture_bundle_accepts_explicit_json_suffix() -> None:
    bundle = load_fixture_bundle("ex0/default.json")

    assert bundle.bundle_name == "ex0/default"
    assert bundle.ex_type == "Ex-0"


@pytest.mark.parametrize(
    "bad_name",
    (
        "",
        "/ex0/default",
        "../default",
        "ex0/../default",
        "ex0/default.txt",
        "unknown/default",
    ),
)
def test_load_fixture_bundle_rejects_bad_names(bad_name: str) -> None:
    with pytest.raises(FixtureLoadError) as exc_info:
        load_fixture_bundle(bad_name)

    assert repr(bad_name) in str(exc_info.value)
