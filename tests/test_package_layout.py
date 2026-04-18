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
        "load_submit_backend_config",
        "BaseSubsystemContext",
        "RuntimeNotConfiguredError",
        "configure_runtime",
        "ReferenceSubsystemTemplate",
        "create_reference_subsystem",
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
        "EntityPreflightResult",
        "EntityRegistryLookup",
        "IngestMetadataLeakError",
        "MissingProducerFieldError",
        "PreflightPolicy",
        "SemanticsError",
        "UnknownExTypeError",
        "ValidationHook",
        "ValidationResult",
        "ValidatorRegistry",
        "assert_ex0_semantic",
        "assert_no_ingest_metadata",
        "assert_producer_only",
        "richer_validation_report",
        "run_entity_preflight",
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
        "build_submit_backend",
        "KafkaBrokerAck",
        "KafkaCompatibleSubmitBackend",
        "KafkaProducerProtocol",
        "MockSubmitBackend",
        "PgSubmitBackend",
        "SubmitBackendHeartbeatAdapter",
        "SubmitBackendConfig",
    ],
    "fixtures": [
        "ContractExample",
        "ContractExampleBundle",
        "FixtureLoadError",
        "available_fixture_bundles",
        "load_fixture_bundle",
    ],
    "testing": [
        "BackendEvent",
        "MockBackend",
        "DEFAULT_SMOKE_BUNDLE_NAMES",
        "build_mock_context",
        "run_subsystem_smoke",
    ],
}


def test_version() -> None:
    assert subsystem_sdk.__version__ == "0.1.0"


def test_root_package_exports_preflight_api() -> None:
    assert subsystem_sdk.EntityPreflightResult.__name__ == "EntityPreflightResult"
    assert hasattr(subsystem_sdk.EntityRegistryLookup, "lookup")
    assert subsystem_sdk.PreflightPolicy
    assert callable(subsystem_sdk.run_entity_preflight)
    assert subsystem_sdk.__all__ == [
        "__version__",
        "EntityPreflightResult",
        "EntityRegistryLookup",
        "PreflightPolicy",
        "run_entity_preflight",
    ]


@pytest.mark.parametrize("subpackage", SUBPACKAGES)
def test_import_subpackage(subpackage: str) -> None:
    module = importlib.import_module(f"subsystem_sdk.{subpackage}")
    assert module.__all__ == EXPECTED_EXPORTS[subpackage]
