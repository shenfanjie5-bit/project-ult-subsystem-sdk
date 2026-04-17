import importlib
from pathlib import Path

import pytest

import subsystem_sdk.base.scaffold as scaffold_module
from subsystem_sdk.base import (
    ReferenceSubsystemTemplate,
    SubsystemRegistrationSpec,
    create_reference_subsystem,
    load_registration_spec,
)


def _registration() -> SubsystemRegistrationSpec:
    return SubsystemRegistrationSpec(
        subsystem_id="subsystem-reference",
        version="0.1.0",
        domain="reference",
        supported_ex_types=["Ex-0", "Ex-1", "Ex-2", "Ex-3"],
        owner="sdk",
        heartbeat_policy_ref="default",
        capabilities={"mode": "reference"},
    )


def test_create_reference_subsystem_writes_expected_files(tmp_path: Path) -> None:
    registration = _registration()

    template = create_reference_subsystem(registration, tmp_path)

    assert isinstance(template, ReferenceSubsystemTemplate)
    assert template.root_dir == tmp_path
    assert template.package_name == "reference_subsystem"
    assert template.registration == registration
    assert template.files
    for path in template.files:
        assert path.exists()
        assert path.is_relative_to(template.root_dir)


def test_create_reference_subsystem_registration_json_roundtrips(
    tmp_path: Path,
) -> None:
    registration = _registration()

    create_reference_subsystem(registration, tmp_path)

    loaded = load_registration_spec(tmp_path / "registration.json")
    assert loaded == registration


def test_create_reference_subsystem_generated_package_imports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_name = "reference_generated"

    create_reference_subsystem(_registration(), tmp_path, package_name=package_name)
    monkeypatch.syspath_prepend(str(tmp_path))
    generated = importlib.import_module(package_name)

    assert generated.load_registration().subsystem_id == "subsystem-reference"
    assert callable(generated.build_context)
    assert callable(generated.example_handler_ex1)
    assert callable(generated.example_handler_ex2)
    assert callable(generated.example_handler_ex3)

    handlers = (tmp_path / package_name / "handlers.py").read_text(encoding="utf-8")
    assert "example_handler_ex1" in handlers
    assert "example_handler_ex2" in handlers
    assert "example_handler_ex3" in handlers
    assert "news" not in handlers
    assert "announcement" not in handlers
    assert "report" not in handlers


def test_create_reference_subsystem_generated_code_has_no_transport_details(
    tmp_path: Path,
) -> None:
    create_reference_subsystem(_registration(), tmp_path)

    generated_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*.py")
    )

    for forbidden in ("pg_table", "queue_table", "kafka_topic", "psycopg"):
        assert forbidden not in generated_text


@pytest.mark.parametrize("package_name", ("", "reference-subsystem", "class", "1sdk"))
def test_create_reference_subsystem_rejects_illegal_package_name(
    tmp_path: Path,
    package_name: str,
) -> None:
    with pytest.raises(ValueError, match="package_name"):
        create_reference_subsystem(
            _registration(),
            tmp_path / "generated",
            package_name=package_name,
        )

    assert not (tmp_path / "generated").exists()


def test_create_reference_subsystem_rejects_nonempty_target_without_overwrite(
    tmp_path: Path,
) -> None:
    existing_file = tmp_path / "keep.txt"
    existing_file.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not empty"):
        create_reference_subsystem(_registration(), tmp_path)

    assert tuple(path.name for path in tmp_path.iterdir()) == ("keep.txt",)


def test_create_reference_subsystem_rejects_template_path_traversal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / "generated"
    monkeypatch.setattr(
        scaffold_module,
        "_TEMPLATE_PATHS",
        (("..", "escape.py.template"),),
    )

    with pytest.raises(ValueError, match="unsafe template path component"):
        create_reference_subsystem(_registration(), target_dir)

    assert not target_dir.exists()
