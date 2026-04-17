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

EXPECTED_PUBLIC_EXPORTS = {
    "validate": [
        "EX0_BANNED_SEMANTICS",
        "EX0_SEMANTIC",
        "INGEST_METADATA_FIELDS",
        "PRODUCER_OWNED_REQUIRED",
        "Ex0SemanticError",
        "IngestMetadataLeakError",
        "MissingProducerFieldError",
        "SemanticsError",
        "assert_ex0_semantic",
        "assert_no_ingest_metadata",
        "assert_producer_only",
    ],
}


def test_version() -> None:
    assert subsystem_sdk.__version__ == "0.1.0"


@pytest.mark.parametrize("subpackage", SUBPACKAGES)
def test_import_subpackage(subpackage: str) -> None:
    module = importlib.import_module(f"subsystem_sdk.{subpackage}")
    assert module.__all__ == EXPECTED_PUBLIC_EXPORTS.get(subpackage, [])
