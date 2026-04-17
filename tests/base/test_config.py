import builtins
from pathlib import Path
from typing import Any

import pytest

from subsystem_sdk.base.config import ConfigLoadError, load_registration_spec


def _top_level_toml() -> str:
    return """
subsystem_id = "subsystem-demo"
version = "0.1.0"
domain = "demo"
supported_ex_types = ["Ex-1", "Ex-2"]
owner = "sdk"
heartbeat_policy_ref = "default"
"""


def test_load_registration_spec_from_top_level_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "registration.toml"
    config_path.write_text(_top_level_toml(), encoding="utf-8")

    spec = load_registration_spec(config_path)

    assert spec.subsystem_id == "subsystem-demo"
    assert spec.supported_ex_types == ("Ex-1", "Ex-2")


def test_load_registration_spec_from_wrapped_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "registration.toml"
    config_path.write_text(
        """
[registration]
subsystem_id = "subsystem-demo"
version = "0.1.0"
domain = "demo"
supported_ex_types = ["Ex-0", "Ex-1"]
owner = "sdk"
heartbeat_policy_ref = "default"

[registration.capabilities]
tier = "local"

[backend]
dsn = "postgres://private"
queue_table = "private_queue"
""",
        encoding="utf-8",
    )

    spec = load_registration_spec(config_path)

    assert spec.supported_ex_types == ("Ex-0", "Ex-1")
    assert spec.capabilities == {"tier": "local"}
    assert "dsn" not in spec.model_dump()
    assert "queue_table" not in spec.model_dump()


def test_load_registration_spec_rejects_unsupported_suffix(tmp_path: Path) -> None:
    config_path = tmp_path / "registration.ini"
    config_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match=".json"):
        load_registration_spec(config_path)


def test_load_registration_spec_from_json(tmp_path: Path) -> None:
    config_path = tmp_path / "registration.json"
    config_path.write_text(
        """
{
  "subsystem_id": "subsystem-demo",
  "version": "0.1.0",
  "domain": "demo",
  "supported_ex_types": ["Ex-0", "Ex-1"],
  "owner": "sdk",
  "heartbeat_policy_ref": "default"
}
""",
        encoding="utf-8",
    )

    spec = load_registration_spec(config_path)

    assert spec.subsystem_id == "subsystem-demo"
    assert spec.supported_ex_types == ("Ex-0", "Ex-1")


def test_load_registration_spec_rejects_non_mapping_config(tmp_path: Path) -> None:
    config_path = tmp_path / "registration.yaml"
    config_path.write_text("- not-a-mapping\n", encoding="utf-8")

    pytest.importorskip("yaml")
    with pytest.raises(ConfigLoadError, match="must be a mapping"):
        load_registration_spec(config_path)


def test_load_registration_spec_from_yaml_when_pyyaml_is_available(
    tmp_path: Path,
) -> None:
    pytest.importorskip("yaml")
    config_path = tmp_path / "registration.yaml"
    config_path.write_text(
        """
registration:
  subsystem_id: subsystem-demo
  version: 0.1.0
  domain: demo
  supported_ex_types:
    - Ex-2
  owner: sdk
  heartbeat_policy_ref: default
""",
        encoding="utf-8",
    )

    spec = load_registration_spec(config_path)

    assert spec.subsystem_id == "subsystem-demo"
    assert spec.supported_ex_types == ("Ex-2",)


def test_load_registration_spec_yaml_missing_dependency_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "registration.yaml"
    config_path.write_text("registration: {}\n", encoding="utf-8")
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "yaml":
            raise ImportError("missing yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ConfigLoadError, match="PyYAML"):
        load_registration_spec(config_path)
