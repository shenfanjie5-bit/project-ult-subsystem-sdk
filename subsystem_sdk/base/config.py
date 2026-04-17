"""Registration config loading helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from subsystem_sdk.backends.config import SubmitBackendConfig
from subsystem_sdk.base.registration import SubsystemRegistrationSpec


class ConfigLoadError(RuntimeError):
    """Raised when a registration config file cannot be loaded."""


def _load_json(path: Path, config_name: str) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(f"invalid JSON {config_name} config: {path}") from exc


def _load_toml(path: Path, config_name: str) -> Any:
    import tomllib

    try:
        with path.open("rb") as file_obj:
            return tomllib.load(file_obj)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigLoadError(f"invalid TOML {config_name} config: {path}") from exc


def _load_yaml(path: Path, config_name: str) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigLoadError(
            f"YAML {config_name} config requires optional PyYAML dependency; "
            "use TOML or install PyYAML to load .yaml/.yml files"
        ) from exc

    try:
        with path.open("r", encoding="utf-8") as file_obj:
            return yaml.safe_load(file_obj)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"invalid YAML {config_name} config: {path}") from exc


def _load_config_file(path: Path, *, config_name: str) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path, config_name)
    if suffix == ".toml":
        return _load_toml(path, config_name)
    if suffix in {".yaml", ".yml"}:
        return _load_yaml(path, config_name)
    raise ConfigLoadError(
        f"unsupported {config_name} config format; "
        "use .json, .toml, .yaml, or .yml"
    )


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


def _backend_data(raw_config: Any, path: Path) -> Mapping[str, Any]:
    if not isinstance(raw_config, Mapping):
        raise ConfigLoadError(f"backend config must be a mapping: {path}")

    wrapped = raw_config.get("backend")
    if wrapped is not None:
        if not isinstance(wrapped, Mapping):
            raise ConfigLoadError(
                f"backend config wrapper must be a mapping: {path}"
            )
        return wrapped

    return raw_config


def load_registration_spec(path: str | Path) -> SubsystemRegistrationSpec:
    """Load a subsystem registration spec from JSON, TOML, or YAML."""

    config_path = Path(path)
    raw_config = _load_config_file(config_path, config_name="registration")

    return SubsystemRegistrationSpec.model_validate(
        dict(_registration_data(raw_config, config_path))
    )


def load_submit_backend_config(path: str | Path) -> SubmitBackendConfig:
    """Load a submit backend config from JSON, TOML, or YAML."""

    config_path = Path(path)
    raw_config = _load_config_file(config_path, config_name="backend")

    return SubmitBackendConfig.model_validate(
        dict(_backend_data(raw_config, config_path))
    )
