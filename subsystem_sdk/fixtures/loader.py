"""Loader for packaged JSON contract example bundles."""

from __future__ import annotations

import json
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath
from typing import Any

from pydantic import ValidationError

from subsystem_sdk.validate.result import ExType

from .bundle import ContractExampleBundle

_DATA_DIR = "data"
_JSON_SUFFIX = ".json"
_EX_TYPE_BY_DIR: dict[str, ExType] = {
    "ex0": "Ex-0",
    "ex1": "Ex-1",
    "ex2": "Ex-2",
    "ex3": "Ex-3",
}


class FixtureLoadError(ValueError):
    """Raised when a packaged fixture bundle cannot be loaded."""


def _fixtures_root() -> Traversable:
    return resources.files("subsystem_sdk.fixtures")


def _normalize_name(name: str) -> tuple[str, tuple[str, ...]]:
    if not isinstance(name, str):
        raise FixtureLoadError(f"fixture bundle name must be a string: {name!r}")

    if not name.strip():
        raise FixtureLoadError(f"fixture bundle name must be non-empty: {name!r}")

    path = PurePosixPath(name)
    if path.is_absolute():
        raise FixtureLoadError(f"fixture bundle name must be relative: {name!r}")

    raw_parts = name.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise FixtureLoadError(f"invalid fixture bundle path: {name!r}")

    if path.suffix and path.suffix != _JSON_SUFFIX:
        raise FixtureLoadError(
            f"fixture bundle resource must be a .json file: {name!r}"
        )

    parts = path.parts
    if parts[-1].endswith(_JSON_SUFFIX):
        parts = (*parts[:-1], parts[-1][: -len(_JSON_SUFFIX)])

    if not parts or parts[-1] == "":
        raise FixtureLoadError(f"invalid fixture bundle path: {name!r}")

    canonical_name = "/".join(parts)
    resource_parts = (*parts[:-1], f"{parts[-1]}{_JSON_SUFFIX}")
    return canonical_name, resource_parts


def _join_resource(root: Traversable, parts: tuple[str, ...]) -> Traversable:
    resource = root
    for part in parts:
        resource = resource.joinpath(part)
    return resource


def _load_json_resource(name: str, resource: Traversable) -> dict[str, Any]:
    if not resource.is_file():
        raise FixtureLoadError(f"fixture bundle not found: {name!r}")

    try:
        loaded = json.loads(resource.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureLoadError(f"fixture bundle JSON is invalid: {name!r}") from exc

    if not isinstance(loaded, dict):
        raise FixtureLoadError(f"fixture bundle JSON must be an object: {name!r}")
    return loaded


def _assert_ex_type_matches_path(name: str, bundle: ContractExampleBundle) -> None:
    ex_dir = name.split("/", 1)[0]
    expected = _EX_TYPE_BY_DIR.get(ex_dir)
    if expected is None:
        raise FixtureLoadError(
            f"fixture bundle path has unknown Ex directory: {name!r}"
        )
    if bundle.ex_type != expected:
        raise FixtureLoadError(
            "fixture bundle ex_type does not match its path: "
            f"{name!r} expected {expected!r}, got {bundle.ex_type!r}"
        )


def load_fixture_bundle(name: str) -> ContractExampleBundle:
    """Load a packaged JSON bundle such as ``ex0/default``."""

    canonical_name, resource_parts = _normalize_name(name)
    resource = _join_resource(_fixtures_root().joinpath(_DATA_DIR), resource_parts)
    raw_bundle = _load_json_resource(name, resource)

    try:
        bundle = ContractExampleBundle.model_validate(raw_bundle)
    except ValidationError as exc:
        raise FixtureLoadError(
            f"fixture bundle structure is invalid: {name!r}"
        ) from exc

    _assert_ex_type_matches_path(canonical_name, bundle)
    return bundle


def _walk_json_bundles(root: Traversable, prefix: tuple[str, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for child in root.iterdir():
        if child.is_dir():
            names.extend(_walk_json_bundles(child, (*prefix, child.name)))
        elif child.is_file() and child.name.endswith(_JSON_SUFFIX):
            names.append("/".join((*prefix, child.name[: -len(_JSON_SUFFIX)])))
    return tuple(names)


def available_fixture_bundles() -> tuple[str, ...]:
    """Return packaged fixture bundle names without the ``.json`` suffix."""

    data_root = _fixtures_root().joinpath(_DATA_DIR)
    if not data_root.is_dir():
        return ()
    return tuple(sorted(_walk_json_bundles(data_root, ())))
