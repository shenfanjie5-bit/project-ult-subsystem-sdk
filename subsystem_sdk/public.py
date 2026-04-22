"""Assembly-facing public entrypoints for subsystem-sdk.

This module is the single boundary that ``assembly`` (registry + compat
checks + bootstrap) imports to introspect this package. The five
``module-level singleton instances`` below match the assembly Protocols
in ``assembly/src/assembly/contracts/entrypoints.py`` and the signature
shape enforced by ``assembly/src/assembly/compat/checks/public_api_boundary.py``:

- ``health_probe.check(*, timeout_sec: float)``
- ``smoke_hook.run(*, profile_id: str)``
- ``init_hook.initialize(*, resolved_env: dict[str, str])``
- ``version_declaration.declare()``
- ``cli.invoke(argv: list[str])``

CLAUDE.md guardrails this file enforces by construction:
- No Layer B authoritative validation, no canonical_entity_id minting,
  no PG / Kafka private fields, no Ex schema redefinition. Every public
  entrypoint here only touches subsystem-sdk's own validators / receipt
  contracts; ``contracts.schemas.ex_payloads`` is the single source of
  truth and is loaded lazily through subsystem_sdk._contracts (the
  designated gateway).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any, Final

from subsystem_sdk import __version__ as _SUBSYSTEM_SDK_VERSION
from subsystem_sdk.submit.receipt import (
    BACKEND_KINDS,
    RESERVED_PRIVATE_KEYS,
)
from subsystem_sdk.validate.semantics import (
    EX0_SEMANTIC,
    INGEST_METADATA_FIELDS,
    PRODUCER_OWNED_REQUIRED,
    IngestMetadataLeakError,
    assert_no_ingest_metadata,
    assert_producer_only,
)


_HEALTHY: Final[str] = "healthy"
_DEGRADED: Final[str] = "degraded"
_DOWN: Final[str] = "blocked"

# Stage 4 §4.1.5: contract_version is the canonical contracts schema version
# this module is bound against (NOT this module's own package version, which
# stays in module_version). Harmonized to v0.1.3 across all 11 active
# subsystem modules so assembly's ContractsVersionCheck (strict equality vs
# matrix.contract_version) succeeds at the cross-project compat audit
# (assembly/scripts/stage_3_compat_audit.py + Stage 4 §4.1 registry).
# Previously this was derived dynamically via subsystem_sdk._contracts
# .get_schema_version, which returns "unknown" today because the contracts
# Ex models don't expose a `schema_version` class attribute — assembly's
# VersionInfo regex `^v\d+\.\d+\.\d+$` rejects "unknown", breaking the
# contract suite. Per Stage 4 §4.1.5 we hardcode the canonical value
# matching the contracts package version this SDK is pinned against.
_CONTRACT_VERSION: Final[str] = "v0.1.3"
_COMPATIBLE_CONTRACT_RANGE: Final[str] = ">=0.1.3,<0.2.0"


def _probe_contracts_schema_gateway() -> dict[str, Any]:
    """Lightly check that ``subsystem_sdk._contracts`` can resolve Ex-0..3.

    Codex review #11 P2 fix: tag the failure ``kind`` so the caller can
    distinguish (a) external ``contracts`` package not installed
    (offline-first — degraded) from (b) ``subsystem_sdk._contracts``
    itself broken or schema lookup raising (real SDK regression —
    blocked). Previously all ``available=False`` paths were uniformly
    treated as ``degraded`` by the caller, masking sdk-side regressions.

    Returns ``kind`` ∈ ``{sdk_internal_broken, contracts_missing,
    schema_lookup_failed}`` whenever ``available`` is False.
    """

    try:
        from subsystem_sdk._contracts import (
            SUPPORTED_EX_TYPES,
            ContractsUnavailableError,
            get_ex_schema,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "available": False,
            "kind": "sdk_internal_broken",
            "reason": f"could not import subsystem_sdk._contracts: {exc!r}",
        }

    try:
        resolved = {ex_type: get_ex_schema(ex_type).__name__ for ex_type in SUPPORTED_EX_TYPES}
    except ContractsUnavailableError as exc:
        return {
            "available": False,
            "kind": "contracts_missing",
            "reason": f"contracts package not installed: {exc}",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "available": False,
            "kind": "schema_lookup_failed",
            "reason": f"contracts schema lookup failed: {exc!r}",
        }

    return {"available": True, "ex_types_resolved": resolved}


class _HealthProbe:
    """Probe SDK-internal invariants without doing any network IO.

    `check(*, timeout_sec)` asserts the invariants by *running them
    against synthetic minimal inputs*; the timeout argument is accepted
    for assembly Protocol compliance but unused — none of these checks
    do IO. Returns a structured dict with status one of
    ``healthy`` / ``degraded`` / ``down``.
    """

    _PROBE_NAME: Final[str] = "subsystem_sdk.health"

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        # Stage 4 §4.3 Lite-stack e2e fix: assembly's
        # ``HealthResult.model_validate`` requires ``module_id`` /
        # ``probe_name`` / ``latency_ms`` / ``message`` plus a status
        # enum value in {healthy, degraded, blocked} (NOT ``"down"``).
        from time import perf_counter

        started_at = perf_counter()
        details: dict[str, Any] = {"timeout_sec": timeout_sec}

        # Invariant 1: INGEST_METADATA_FIELDS is non-empty + the rejector
        # actually rejects them.
        try:
            assert INGEST_METADATA_FIELDS, "INGEST_METADATA_FIELDS empty"
            try:
                assert_no_ingest_metadata({"submitted_at": "2026-01-01T00:00:00Z"})
            except IngestMetadataLeakError:
                details["ingest_metadata_guard"] = "ok"
            else:
                details["ingest_metadata_guard"] = (
                    "FAIL — assert_no_ingest_metadata accepted submitted_at"
                )
                return self._build_result(
                    started_at,
                    status=_DOWN,
                    message=(
                        "subsystem-sdk INGEST_METADATA_FIELDS guard accepted "
                        "ingest metadata key — invariant broken"
                    ),
                    details=details,
                )
        except Exception as exc:  # pragma: no cover - defensive
            details["ingest_metadata_guard"] = f"FAIL: {exc!r}"
            return self._build_result(
                started_at,
                status=_DOWN,
                message=f"subsystem-sdk health probe raised: {exc!r}",
                details=details,
            )

        # Invariant 2: contracts schema gateway. Codex review #11 P2 fix:
        # branch on ``kind`` instead of treating every ``available=False``
        # uniformly as ``degraded``. Only ``contracts_missing`` (external
        # contracts package not installed in this venv) is offline-first
        # benign; ``sdk_internal_broken`` and ``schema_lookup_failed``
        # are real SDK-side regressions (the gateway module itself can't
        # import, or it raises during schema resolution) and must surface
        # as ``blocked`` so assembly's gate doesn't silently let them
        # through as degraded.
        gateway = _probe_contracts_schema_gateway()
        details["contracts_schema_gateway"] = gateway
        if gateway["available"]:
            status = _HEALTHY
            message = "subsystem-sdk invariants verified (contracts gateway available)"
        else:
            kind = gateway.get("kind")
            if kind == "contracts_missing":
                status = _DEGRADED
                message = (
                    "subsystem-sdk running offline-first — external "
                    "contracts package not installed in this venv"
                )
            else:
                # sdk_internal_broken / schema_lookup_failed / unknown —
                # SDK-side regression, not environmental.
                return self._build_result(
                    started_at,
                    status=_DOWN,
                    message=(
                        f"subsystem-sdk contracts schema gateway broken "
                        f"(kind={kind!r}); not an offline-first state — "
                        "SDK-side regression"
                    ),
                    details=details,
                )

        # Invariant 3: SDK declares the canonical 4 Ex types and 3 backend kinds.
        details["supported_ex_types"] = sorted(PRODUCER_OWNED_REQUIRED.keys())
        details["backend_kinds"] = list(BACKEND_KINDS)
        details["ex0_semantic"] = EX0_SEMANTIC

        return self._build_result(
            started_at,
            status=status,
            message=message,
            details=details,
        )

    def _build_result(
        self,
        started_at: float,
        *,
        status: str,
        message: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        from time import perf_counter

        return {
            "module_id": "subsystem-sdk",
            "probe_name": self._PROBE_NAME,
            "status": status,
            "latency_ms": max(0.0, (perf_counter() - started_at) * 1000.0),
            "message": message,
            "details": details,
        }


class _SmokeHook:
    """Run a one-shot end-to-end smoke that exercises the SDK's public
    surface (validate + heartbeat shape + receipt contract) without
    starting any real backend. Profile-aware only insofar as it rejects
    unknown profile_ids — Lite/Full profile selection happens via
    ``backends.config.SubmitBackendConfig``, not via this hook.
    """

    _SUPPORTED_PROFILES: Final[frozenset[str]] = frozenset(
        {"lite-local", "full-dev"}
    )

    def run(self, *, profile_id: str) -> dict[str, Any]:
        if profile_id not in self._SUPPORTED_PROFILES:
            return {
                "passed": False,
                "failure_reason": (
                    f"unknown profile_id={profile_id!r}; supported: "
                    f"{sorted(self._SUPPORTED_PROFILES)}"
                ),
                "profile_id": profile_id,
            }

        from datetime import UTC, datetime

        from subsystem_sdk.backends.heartbeat import (
            SubmitBackendHeartbeatAdapter,
        )
        from subsystem_sdk.backends.mock import MockSubmitBackend
        from subsystem_sdk.heartbeat.client import HeartbeatClient
        from subsystem_sdk.heartbeat.payload import build_ex0_payload
        from subsystem_sdk.validate.engine import validate_payload

        # Smoke exercises the FULL Ex-0 path the SDK exposes to producers:
        #   build_ex0_payload  →  validate_payload  →
        #   HeartbeatClient.send_heartbeat  →  SubmitReceipt
        # If contracts is installed, validate_payload model_validates the
        # wire payload against ``contracts.schemas.Ex0Metadata`` — that
        # is the path Layer B itself uses, so the smoke is a true round-
        # trip check of (SDK builder + SDK validator + contracts schema +
        # SDK receipt contract). If contracts is NOT installed (offline
        # dev venv), validate_payload reports an "unavailable" field
        # error and the smoke fails — that's correct: a SDK without
        # contracts can't actually send Ex-0 anywhere usable.

        # 1. Build the wire-format Ex-0 payload (status enum mapped to
        #    contracts.core.types.HeartbeatStatus values; SDK envelope
        #    fields stay for SDK-internal routing and get stripped at
        #    the validate_payload boundary).
        ex0_payload = build_ex0_payload(
            subsystem_id="smoke-subsystem",
            version="0.0.0",
            status="healthy",
            heartbeat_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        # 2. assert_producer_only — Ex-0 semantic + producer-owned-only
        #    + no ingest metadata leak. Real call into runtime.
        try:
            assert_producer_only(ex0_payload)
        except Exception as exc:
            return {
                "passed": False,
                "failure_reason": (
                    f"assert_producer_only failed on clean Ex-0 payload: {exc!r}"
                ),
                "profile_id": profile_id,
            }

        # 3. validate_payload — REAL contracts model_validate (envelope
        #    stripped inside the engine before model_validate is called).
        #    Failing here means the SDK's wire contract with Layer B is
        #    broken; smoke MUST surface this, not paper over it.
        validation = validate_payload(ex0_payload)
        if not validation.is_valid:
            return {
                "passed": False,
                "failure_reason": (
                    "validate_payload rejected SDK-built Ex-0 wire payload; "
                    "this is a real cross-repo SDK<->contracts incompatibility, "
                    "NOT a smoke setup issue. Field errors: "
                    f"{list(validation.field_errors)}"
                ),
                "profile_id": profile_id,
                "details": {
                    "validation_ex_type": validation.ex_type,
                    "validation_schema_version": validation.schema_version,
                    "wire_payload_keys": sorted(ex0_payload.keys()),
                },
            }

        # 4. HeartbeatClient.send_heartbeat through a MockSubmitBackend —
        #    end-to-end the producer-facing path including receipt
        #    normalization. MockSubmitBackend is in-process (no IO), so
        #    this is fast and transport-agnostic.
        backend = MockSubmitBackend()
        client = HeartbeatClient(SubmitBackendHeartbeatAdapter(backend))
        try:
            receipt = client.send_heartbeat(ex0_payload)
        except Exception as exc:
            return {
                "passed": False,
                "failure_reason": f"send_heartbeat raised: {exc!r}",
                "profile_id": profile_id,
            }
        if not receipt.accepted:
            return {
                "passed": False,
                "failure_reason": (
                    f"send_heartbeat receipt not accepted: errors={list(receipt.errors)}"
                ),
                "profile_id": profile_id,
            }

        # 5. Receipt-shape sanity: RESERVED_PRIVATE_KEYS must be non-empty
        #    and disjoint from INGEST_METADATA_FIELDS (different boundary
        #    layers — backend-private leak vs producer-side ingest leak).
        if not RESERVED_PRIVATE_KEYS:
            return {
                "passed": False,
                "failure_reason": "RESERVED_PRIVATE_KEYS empty",
                "profile_id": profile_id,
            }
        if RESERVED_PRIVATE_KEYS & INGEST_METADATA_FIELDS:
            return {
                "passed": False,
                "failure_reason": (
                    "RESERVED_PRIVATE_KEYS overlaps INGEST_METADATA_FIELDS; "
                    "two distinct boundary layers must stay disjoint"
                ),
                "profile_id": profile_id,
            }

        # 6. Negative-path guard exercise — assert_no_ingest_metadata MUST
        #    raise on each of the forbidden fields. Anchors the iron rule
        #    that the guard hasn't been silently weakened.
        for forbidden_field in ("submitted_at", "ingest_seq"):
            polluted = dict(ex0_payload, **{forbidden_field: "leak"})
            try:
                assert_no_ingest_metadata(polluted)
            except IngestMetadataLeakError:
                continue
            return {
                "passed": False,
                "failure_reason": (
                    f"ingest-metadata guard let {forbidden_field!r} through; "
                    "iron rule violation (CLAUDE.md: producer payload must "
                    "never contain ingest metadata)"
                ),
                "profile_id": profile_id,
            }

        return {
            "passed": True,
            "profile_id": profile_id,
            "details": {
                "validation_ex_type": validation.ex_type,
                "validation_schema_version": validation.schema_version,
                "receipt_id": receipt.receipt_id,
                "receipt_backend_kind": receipt.backend_kind,
                "receipt_validator_version": receipt.validator_version,
                "wire_payload_status": ex0_payload["status"],
                "ex0_payload_fields": sorted(ex0_payload.keys()),
                "ingest_metadata_fields_checked": ["submitted_at", "ingest_seq"],
                "reserved_private_keys_count": len(RESERVED_PRIVATE_KEYS),
                "ex0_semantic": EX0_SEMANTIC,
            },
        }


class _InitHook:
    """No-op initialization. subsystem-sdk has no global mutable state to
    set up at bootstrap (backends are wired per-call via SubmitClient or
    via the runtime singleton at the consumer's choice). Returns ``None``
    per assembly Protocol; ``resolved_env`` is accepted for compliance.
    """

    def initialize(self, *, resolved_env: dict[str, str]) -> None:
        # Reading resolved_env is fine; mutating module/global state is
        # not. Keep this body trivial so the bootstrap order can't depend
        # on subsystem-sdk having "warmed up".
        _ = resolved_env
        return None


class _VersionDeclaration:
    """Declare the subsystem-sdk + contracts schema versions assembly
    should reconcile in the registry. Returns a stable dict shape:

        {
            "module_id": "subsystem-sdk",
            "module_version": "<package version>",
            "contract_version": "<contracts schema version or 'unknown'>",
            "supported_ex_types": [...],
            "backend_kinds": [...],
        }
    """

    def declare(self) -> dict[str, Any]:
        return {
            "module_id": "subsystem-sdk",
            "module_version": _SUBSYSTEM_SDK_VERSION,
            "contract_version": _CONTRACT_VERSION,
            "compatible_contract_range": _COMPATIBLE_CONTRACT_RANGE,
            "supported_ex_types": sorted(PRODUCER_OWNED_REQUIRED.keys()),
            "backend_kinds": list(BACKEND_KINDS),
            "ex0_semantic": EX0_SEMANTIC,
        }


class _Cli:
    """Tiny SDK CLI for assembly's smoke probes; intentionally minimal to
    keep iron rule #2 boundary (no business logic in CLI). Supported argv:

    - ``["version"]`` — print version_declaration JSON to stdout, exit 0
    - ``["health", "--timeout-sec", "<float>"]`` — print health JSON, exit
      0 on healthy/degraded, 1 on down
    - ``["smoke", "--profile-id", "<id>"]`` — print smoke JSON, exit 0 on
      passed, 1 on failed
    """

    def invoke(self, argv: list[str]) -> int:
        if not argv:
            sys.stderr.write("usage: subsystem-sdk-cli {version|health|smoke} [args]\n")
            return 2

        command = argv[0]
        rest = argv[1:]

        if command == "version":
            sys.stdout.write(json.dumps(version_declaration.declare()) + "\n")
            return 0

        if command == "health":
            timeout_sec = self._parse_kw_float(rest, "--timeout-sec", default=1.0)
            if timeout_sec is None:
                return 2
            result = health_probe.check(timeout_sec=timeout_sec)
            sys.stdout.write(json.dumps(result) + "\n")
            return 0 if result["status"] in {_HEALTHY, _DEGRADED} else 1

        if command == "smoke":
            profile_id = self._parse_kw_str(rest, "--profile-id", default=None)
            if profile_id is None:
                sys.stderr.write("smoke requires --profile-id <id>\n")
                return 2
            result = smoke_hook.run(profile_id=profile_id)
            sys.stdout.write(json.dumps(result) + "\n")
            return 0 if result.get("passed") else 1

        sys.stderr.write(f"unknown command: {command!r}\n")
        return 2

    @staticmethod
    def _parse_kw_float(rest: list[str], flag: str, *, default: float) -> float | None:
        if flag not in rest:
            return default
        idx = rest.index(flag)
        if idx + 1 >= len(rest):
            sys.stderr.write(f"{flag} requires a value\n")
            return None
        try:
            return float(rest[idx + 1])
        except ValueError:
            sys.stderr.write(f"{flag} must be a float; got {rest[idx + 1]!r}\n")
            return None

    @staticmethod
    def _parse_kw_str(rest: list[str], flag: str, *, default: str | None) -> str | None:
        if flag not in rest:
            return default
        idx = rest.index(flag)
        if idx + 1 >= len(rest):
            sys.stderr.write(f"{flag} requires a value\n")
            return None
        return rest[idx + 1]


# Module-level singleton instances — assembly registry references these
# by their lowercase attribute names (not the underscore-prefixed classes).
health_probe = _HealthProbe()
smoke_hook = _SmokeHook()
init_hook = _InitHook()
version_declaration = _VersionDeclaration()
cli = _Cli()


__all__ = [
    "cli",
    "health_probe",
    "init_hook",
    "smoke_hook",
    "version_declaration",
]
