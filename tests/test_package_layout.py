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
    "base": [
        "SubsystemRegistrationSpec",
        "RegistrationRegistry",
        "RegistrationError",
        "register_subsystem",
        "get_registered_subsystem",
        "load_registration_spec",
        "BaseSubsystemContext",
        "SubsystemBaseInterface",
        "BaseSubsystem",
    ],
    "validate": [
        "ContractsSchemaError",
        "ContractsUnavailableError",
        "EX0_BANNED_SEMANTICS",
        "EX0_SEMANTIC",
        "INGEST_METADATA_FIELDS",
        "PRODUCER_OWNED_REQUIRED",
        "Ex0SemanticError",
        "IngestMetadataLeakError",
        "MissingProducerFieldError",
        "SemanticsError",
        "UnknownExTypeError",
        "ValidationHook",
        "ValidationResult",
        "ValidatorRegistry",
        "assert_ex0_semantic",
        "assert_no_ingest_metadata",
        "assert_producer_only",
        "validate_payload",
    ],
    "submit": [
        "BACKEND_KINDS",
        "RESERVED_PRIVATE_KEYS",
        "BackendKind",
        "SubmitBackendInterface",
        "SubmitClient",
        "SubmitReceipt",
        "assert_no_private_leak",
        "normalize_backend_receipt",
        "normalize_receipt",
        "submit",
    ],
    "heartbeat": [
        "DEFAULT_HEARTBEAT_POLICY",
        "HeartbeatBackendInterface",
        "HeartbeatClient",
        "HeartbeatPolicy",
        "HeartbeatState",
        "HeartbeatStatus",
        "build_ex0_payload",
        "send_heartbeat",
    ],
    "backends": [
        "MockSubmitBackend",
        "PgSubmitBackend",
        "SubmitBackendConfig",
    ],
    "fixtures": [],
    "testing": [],
}


def test_version() -> None:
    assert subsystem_sdk.__version__ == "0.1.0"


@pytest.mark.parametrize("subpackage", SUBPACKAGES)
def test_import_subpackage(subpackage: str) -> None:
    module = importlib.import_module(f"subsystem_sdk.{subpackage}")
    assert module.__all__ == EXPECTED_EXPORTS[subpackage]
