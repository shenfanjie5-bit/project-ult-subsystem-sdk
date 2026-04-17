"""Reference subsystem scaffold generation."""

from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from string import Template
from typing import Final

from subsystem_sdk.base.registration import SubsystemRegistrationSpec

_PACKAGE_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TEMPLATE_SUFFIX: Final[str] = ".template"
_PACKAGE_PLACEHOLDER: Final[str] = "<package>"
_TEMPLATE_PATHS: Final[tuple[tuple[str, ...], ...]] = (
    ("pyproject.toml.template",),
    ("README.md.template",),
    ("registration.json.template",),
    (_PACKAGE_PLACEHOLDER, "__init__.py.template"),
    (_PACKAGE_PLACEHOLDER, "handlers.py.template"),
    (_PACKAGE_PLACEHOLDER, "runtime.py.template"),
)


@dataclass(frozen=True)
class ReferenceSubsystemTemplate:
    """Result returned after generating a reference subsystem skeleton."""

    root_dir: Path
    package_name: str
    files: tuple[Path, ...]
    registration: SubsystemRegistrationSpec


def _validate_package_name(package_name: str) -> None:
    if not _PACKAGE_NAME_RE.fullmatch(package_name) or keyword.iskeyword(package_name):
        raise ValueError(
            "package_name must be a valid, non-keyword Python identifier"
        )


def _validate_template_parts(parts: tuple[str, ...]) -> None:
    if not parts:
        raise ValueError("template path must not be empty")

    for part in parts:
        if part in {"", ".", ".."}:
            raise ValueError(f"unsafe template path component: {part!r}")
        path = PurePosixPath(part)
        if path.is_absolute() or path.parts != (part,):
            raise ValueError(f"unsafe template path component: {part!r}")

    if not parts[-1].endswith(_TEMPLATE_SUFFIX):
        raise ValueError(f"template path must end with {_TEMPLATE_SUFFIX!r}")


def _destination_for_template(
    root_dir: Path,
    parts: tuple[str, ...],
    package_name: str,
) -> Path:
    output_parts = [
        package_name if part == _PACKAGE_PLACEHOLDER else part for part in parts
    ]
    output_parts[-1] = output_parts[-1][: -len(_TEMPLATE_SUFFIX)]
    destination = root_dir.joinpath(*output_parts).resolve(strict=False)
    try:
        destination.relative_to(root_dir)
    except ValueError as exc:
        raise ValueError(f"template path escapes target_dir: {'/'.join(parts)}") from exc
    return destination


def _template_resource(parts: tuple[str, ...]):
    resource = resources.files("subsystem_sdk.fixtures").joinpath(
        "templates",
        "reference_subsystem",
    )
    for part in parts:
        resource = resource.joinpath(part)
    return resource


def _registration_json(spec: SubsystemRegistrationSpec) -> str:
    return json.dumps(
        spec.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    )


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _template_values(
    spec: SubsystemRegistrationSpec,
    package_name: str,
) -> dict[str, str]:
    distribution_name = package_name.replace("_", "-")
    description = f"Reference subsystem skeleton for {spec.subsystem_id}."
    return {
        "description_toml": _toml_string(description),
        "distribution_name": distribution_name,
        "distribution_name_toml": _toml_string(distribution_name),
        "package_include_toml": _toml_string(f"{package_name}*"),
        "package_name": package_name,
        "registration_json": _registration_json(spec),
        "subsystem_id": spec.subsystem_id,
        "version": spec.version,
        "version_toml": _toml_string(spec.version),
    }


def _planned_files(
    root_dir: Path,
    package_name: str,
    values: dict[str, str],
) -> tuple[tuple[Path, str], ...]:
    planned: list[tuple[Path, str]] = []
    for template_parts in _TEMPLATE_PATHS:
        _validate_template_parts(template_parts)
        destination = _destination_for_template(root_dir, template_parts, package_name)
        resource = _template_resource(template_parts)
        if not resource.is_file():
            raise ValueError(f"reference subsystem template not found: {template_parts}")
        rendered = Template(resource.read_text(encoding="utf-8")).substitute(values)
        planned.append((destination, rendered))
    return tuple(planned)


def create_reference_subsystem(
    spec: SubsystemRegistrationSpec,
    target_dir: str | Path,
    *,
    package_name: str = "reference_subsystem",
    overwrite: bool = False,
) -> ReferenceSubsystemTemplate:
    """Generate a small reference subsystem package inside ``target_dir``."""

    _validate_package_name(package_name)
    root_dir = Path(target_dir).resolve(strict=False)

    if root_dir.exists():
        if not root_dir.is_dir():
            raise FileExistsError(f"target_dir is not a directory: {root_dir}")
        if not overwrite and any(root_dir.iterdir()):
            raise FileExistsError(
                f"target_dir already exists and is not empty: {root_dir}"
            )

    planned = _planned_files(
        root_dir,
        package_name,
        _template_values(spec, package_name),
    )

    root_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[Path] = []
    for destination, rendered in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        written_files.append(destination)

    return ReferenceSubsystemTemplate(
        root_dir=root_dir,
        package_name=package_name,
        files=tuple(written_files),
        registration=spec,
    )
