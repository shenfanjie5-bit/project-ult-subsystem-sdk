import importlib

import pytest

import subsystem_sdk


SUBPACKAGES = (
    "base",
    "validate",
    "submit",
    "heartbeat",
    "backends",
    "fixtures",
    "testing",
)

EXPECTED_EXPORTS = {
    "base": [],
    "validate": ["ValidationResult"],
    "submit": [
        "BACKEND_KINDS",
        "RESERVED_PRIVATE_KEYS",
        "BackendKind",
        "SubmitReceipt",
        "assert_no_private_leak",
        "normalize_receipt",
    ],
    "heartbeat": [],
    "backends": [],
    "fixtures": [],
    "testing": [],
}


def test_version() -> None:
    assert subsystem_sdk.__version__ == "0.1.0"


@pytest.mark.parametrize("subpackage", SUBPACKAGES)
def test_import_subpackage(subpackage: str) -> None:
    module = importlib.import_module(f"subsystem_sdk.{subpackage}")
    assert module.__all__ == EXPECTED_EXPORTS[subpackage]
