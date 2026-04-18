from pathlib import Path

import pytest
from pydantic import ValidationError

from subsystem_sdk.fixtures import ContractExample, ContractExampleBundle
from subsystem_sdk.fixtures.loader import available_fixture_bundles, load_fixture_bundle
from subsystem_sdk.validate import EX0_SEMANTIC, INGEST_METADATA_FIELDS


RULE_NOTE_MARKERS = (
    "Ingest metadata guard",
    "Ex-0 semantic guard",
    "Producer-owned required field guard",
    "Unknown Ex type guard",
    "Ex type mismatch guard",
)
FORBIDDEN_BUSINESS_TERMS = (
    "news",
    "announcement",
    "research report",
    "公告",
    "研报",
)


def test_contract_example_requires_non_empty_fields() -> None:
    with pytest.raises(ValidationError, match="name must be non-empty"):
        ContractExample(name=" ", payload={"ex_type": "Ex-1"}, notes="valid note")

    with pytest.raises(ValidationError, match="payload must be non-empty"):
        ContractExample(name="example", payload={}, notes="valid note")

    with pytest.raises(ValidationError, match="notes must be non-empty"):
        ContractExample(name="example", payload={"ex_type": "Ex-1"}, notes="")


def test_contract_example_and_bundle_are_frozen() -> None:
    example = ContractExample(
        name="example",
        payload={"ex_type": "Ex-1", "nested": {"value": "placeholder"}},
        notes="valid note",
    )
    bundle = ContractExampleBundle(
        bundle_name="ex1/default",
        ex_type="Ex-1",
        valid_examples=(example,),
        invalid_examples=(example,),
    )

    with pytest.raises((ValidationError, TypeError)):
        example.name = "changed"

    with pytest.raises((ValidationError, TypeError)):
        bundle.bundle_name = "changed"

    with pytest.raises(TypeError):
        example.payload["new"] = "value"  # type: ignore[index]

    with pytest.raises(TypeError):
        example.payload["nested"]["value"] = "changed"  # type: ignore[index]


def test_bundle_model_dump_json_mode_is_json_safe() -> None:
    bundle = load_fixture_bundle("ex0/default")

    dumped = bundle.model_dump(mode="json")

    assert isinstance(dumped, dict)
    assert isinstance(dumped["valid_examples"], list)
    assert isinstance(dumped["valid_examples"][0]["payload"], dict)
    assert isinstance(dumped["valid_examples"][0]["payload"]["pending_count"], int)


def test_bundle_rejects_valid_example_with_wrong_ex_type() -> None:
    with pytest.raises(ValidationError, match="must match bundle ex_type"):
        ContractExampleBundle(
            bundle_name="ex1/default",
            ex_type="Ex-1",
            valid_examples=(
                ContractExample(
                    name="wrong-ex-type",
                    payload={"ex_type": "Ex-2", "subsystem_id": "subsystem-demo"},
                    notes="Valid examples must match bundle metadata.",
                ),
            ),
            invalid_examples=(),
        )


@pytest.mark.parametrize("bundle_name", available_fixture_bundles())
def test_default_bundle_data_meets_coverage_rules(bundle_name: str) -> None:
    bundle = load_fixture_bundle(bundle_name)

    assert len(bundle.valid_examples) >= 2
    assert len(bundle.invalid_examples) >= 3

    for example in bundle.valid_examples:
        assert not set(example.payload).intersection(INGEST_METADATA_FIELDS)
        if bundle.ex_type == "Ex-0":
            assert example.payload["semantic"] == EX0_SEMANTIC

    for example in bundle.invalid_examples:
        assert example.notes.strip()
        assert any(marker in example.notes for marker in RULE_NOTE_MARKERS)


def test_default_fixture_data_avoids_specific_business_terms() -> None:
    serialized = "\n".join(
        str(load_fixture_bundle(name).model_dump(mode="json"))
        for name in available_fixture_bundles()
    ).lower()

    for term in FORBIDDEN_BUSINESS_TERMS:
        assert term not in serialized


def test_fixtures_runtime_does_not_define_second_schema_classes(
    PROJECT_ROOT: Path,
) -> None:
    fixtures_dir = PROJECT_ROOT / "subsystem_sdk" / "fixtures"
    source_text = "\n".join(
        path.read_text(encoding="utf-8") for path in fixtures_dir.rglob("*.py")
    )

    for class_name in ("Ex0Payload", "Ex1Payload", "Ex2Payload", "Ex3Payload"):
        assert f"class {class_name}" not in source_text
