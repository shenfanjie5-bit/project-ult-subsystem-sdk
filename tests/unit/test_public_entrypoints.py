"""Unit tier — public.py module-level singletons + signature shapes.

Iron rule check: public entrypoints must be **class instances** with
specific method names + KEYWORD_ONLY param names matching exactly what
``assembly/src/assembly/compat/checks/public_api_boundary.py`` enforces
(``_validate_entrypoint_signature``). If signatures drift, assembly's
real PublicApiBoundaryCheck would fail with ``isinstance(loaded, Protocol)``
or signature-mismatch errors — so this unit tier mirrors those checks
locally to fail fast.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from subsystem_sdk import public


class TestModuleLevelSingletons:
    """assembly references entrypoints by lowercase attribute names."""

    def test_health_probe_is_module_level_instance(self) -> None:
        assert hasattr(public, "health_probe")
        assert not inspect.isclass(public.health_probe)
        assert hasattr(public.health_probe, "check")

    def test_smoke_hook_is_module_level_instance(self) -> None:
        assert hasattr(public, "smoke_hook")
        assert not inspect.isclass(public.smoke_hook)
        assert hasattr(public.smoke_hook, "run")

    def test_init_hook_is_module_level_instance(self) -> None:
        assert hasattr(public, "init_hook")
        assert not inspect.isclass(public.init_hook)
        assert hasattr(public.init_hook, "initialize")

    def test_version_declaration_is_module_level_instance(self) -> None:
        assert hasattr(public, "version_declaration")
        assert not inspect.isclass(public.version_declaration)
        assert hasattr(public.version_declaration, "declare")

    def test_cli_is_module_level_instance(self) -> None:
        assert hasattr(public, "cli")
        assert not inspect.isclass(public.cli)
        assert hasattr(public.cli, "invoke")

    def test_dunder_all_lists_exactly_five_singletons(self) -> None:
        # If a 6th entrypoint kind shows up, assembly's PublicEntrypoint
        # enum + Protocol set must add it first; flag stage-2 drift here.
        assert sorted(public.__all__) == sorted(
            ["cli", "health_probe", "init_hook", "smoke_hook", "version_declaration"]
        )


class TestEntrypointSignaturesMatchAssemblyProtocol:
    """Mirror ``assembly._validate_entrypoint_signature`` locally — every
    parameter must be KEYWORD_ONLY (except ``cli.invoke``'s ``argv`` which
    is POSITIONAL_OR_KEYWORD), required (no default), and named exactly
    what assembly expects.
    """

    @staticmethod
    def _params_excluding_self(method: Any) -> list[inspect.Parameter]:
        sig = inspect.signature(method)
        return [
            p for name, p in sig.parameters.items() if name != "self"
        ]

    def test_health_probe_check_signature(self) -> None:
        params = self._params_excluding_self(public.health_probe.check)
        assert len(params) == 1
        (timeout_sec,) = params
        assert timeout_sec.name == "timeout_sec"
        assert timeout_sec.kind is inspect.Parameter.KEYWORD_ONLY
        assert timeout_sec.default is inspect.Parameter.empty

    def test_smoke_hook_run_signature(self) -> None:
        params = self._params_excluding_self(public.smoke_hook.run)
        assert len(params) == 1
        (profile_id,) = params
        assert profile_id.name == "profile_id"
        assert profile_id.kind is inspect.Parameter.KEYWORD_ONLY
        assert profile_id.default is inspect.Parameter.empty

    def test_init_hook_initialize_signature(self) -> None:
        params = self._params_excluding_self(public.init_hook.initialize)
        assert len(params) == 1
        (resolved_env,) = params
        assert resolved_env.name == "resolved_env"
        assert resolved_env.kind is inspect.Parameter.KEYWORD_ONLY
        assert resolved_env.default is inspect.Parameter.empty

    def test_version_declaration_declare_signature(self) -> None:
        params = self._params_excluding_self(public.version_declaration.declare)
        assert params == []

    def test_cli_invoke_signature(self) -> None:
        params = self._params_excluding_self(public.cli.invoke)
        assert len(params) == 1
        (argv,) = params
        assert argv.name == "argv"
        assert argv.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert argv.default is inspect.Parameter.empty


class TestEntrypointBehaviour:
    """Light behaviour smoke — ensures the singletons actually work end-
    to-end (not just have the right shape). Goes through public.py only;
    no direct touch of internal classes.
    """

    def test_health_probe_returns_status_dict(self) -> None:
        result = public.health_probe.check(timeout_sec=1.0)
        assert isinstance(result, dict)
        assert result["status"] in {"healthy", "degraded", "blocked"}
        assert "details" in result
        assert result["details"]["timeout_sec"] == 1.0

    def test_smoke_hook_runs_against_supported_profiles(self) -> None:
        for profile_id in ("lite-local", "full-dev"):
            result = public.smoke_hook.run(profile_id=profile_id)
            assert result["passed"], result.get("failure_reason")
            assert set(result) == {
                "module_id",
                "hook_name",
                "passed",
                "duration_ms",
                "failure_reason",
            }
            assert result["module_id"] == "subsystem-sdk"
            assert result["hook_name"] == "subsystem_sdk.smoke"
            assert result["failure_reason"] is None

    def test_smoke_hook_rejects_unknown_profile(self) -> None:
        result = public.smoke_hook.run(profile_id="nonsense-profile")
        assert set(result) == {
            "module_id",
            "hook_name",
            "passed",
            "duration_ms",
            "failure_reason",
        }
        assert result["passed"] is False
        assert "unknown profile_id" in result["failure_reason"]

    def test_init_hook_returns_none(self) -> None:
        assert public.init_hook.initialize(resolved_env={}) is None

    def test_version_declaration_returns_expected_shape(self) -> None:
        result = public.version_declaration.declare()
        assert result["module_id"] == "subsystem-sdk"
        assert result["module_version"]
        assert "contract_version" in result
        # Must include 4 supported Ex types in stable order.
        assert result["supported_ex_types"] == ["Ex-0", "Ex-1", "Ex-2", "Ex-3"]
        # Must list 3 backend kinds (lite_pg, full_kafka, mock).
        assert set(result["backend_kinds"]) == {"lite_pg", "full_kafka", "mock"}
        assert result["ex0_semantic"] == "metadata_or_heartbeat"

    def test_public_entrypoints_validate_against_assembly_models(self) -> None:
        assembly_models = pytest.importorskip("assembly.contracts.models")

        assembly_models.HealthResult.model_validate(
            public.health_probe.check(timeout_sec=1.0)
        )
        assembly_models.SmokeResult.model_validate(
            public.smoke_hook.run(profile_id="lite-local")
        )
        assembly_models.SmokeResult.model_validate(
            public.smoke_hook.run(profile_id="full-dev")
        )
        assembly_models.SmokeResult.model_validate(
            public.smoke_hook.run(profile_id="nonsense-profile")
        )
        assembly_models.VersionInfo.model_validate(
            public.version_declaration.declare()
        )

    def test_cli_version_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = public.cli.invoke(["version"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "subsystem-sdk" in out

    def test_cli_health_returns_zero_when_healthy_or_degraded(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = public.cli.invoke(["health"])
        out = capsys.readouterr().out
        assert rc == 0
        assert '"status"' in out

    def test_cli_unknown_command_returns_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = public.cli.invoke(["nope"])
        assert rc == 2
        assert "unknown command" in capsys.readouterr().err
