"""Registration config loading helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from subsystem_sdk.base.registration import SubsystemRegistrationSpec


class ConfigLoadError(RuntimeError):
    """Raised when a registration config file cannot be loaded."""


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(f"invalid JSON registration config: {path}") from exc


def _load_toml(path: Path) -> Any:
    import tomllib

    try:
        with path.open("rb") as file_obj:
            return tomllib.load(file_obj)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigLoadError(f"invalid TOML registration config: {path}") from exc


def _load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigLoadError(
            "YAML registration config requires optional PyYAML dependency; "
            "use TOML or install PyYAML to load .yaml/.yml files"
        ) from exc

    try:
        with path.open("r", encoding="utf-8") as file_obj:
            return yaml.safe_load(file_obj)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"invalid YAML registration config: {path}") from exc


def _registration_data(raw_config: Any, path: Path) -> Mapping[str, Any]:
    if not isinstance(raw_config, Mapping):
        raise ConfigLoadError(
            f"registration config must be a mapping: {path}"
        )

    wrapped = raw_config.get("registration")
    if wrapped is not None:
        if not isinstance(wrapped, Mapping):
            raise ConfigLoadError(
                f"registration config wrapper must be a mapping: {path}"
            )
        return wrapped

    return raw_config


def load_registration_spec(path: str | Path) -> SubsystemRegistrationSpec:
    """Load a subsystem registration spec from JSON, TOML, or YAML."""

    config_path = Path(path)
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        raw_config = _load_json(config_path)
    elif suffix == ".toml":
        raw_config = _load_toml(config_path)
    elif suffix in {".yaml", ".yml"}:
        raw_config = _load_yaml(config_path)
    else:
        raise ConfigLoadError(
            "unsupported registration config format; "
            "use .json, .toml, .yaml, or .yml"
        )

    return SubsystemRegistrationSpec.model_validate(
        dict(_registration_data(raw_config, config_path))
    )
