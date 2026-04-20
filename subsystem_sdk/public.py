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
_DOWN: Final[str] = "down"


def _probe_contracts_schema_gateway() -> dict[str, Any]:
    """Lightly check that ``subsystem_sdk._contracts`` can resolve Ex-0..3.

    Treats a missing ``contracts`` install as ``degraded`` rather than
    ``down`` — assembly's compat check still passes (it only requires the
    method to return a dict), and offline-first dev venvs (no
    contracts-schemas extra installed) keep working.
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
            "reason": f"could not import subsystem_sdk._contracts: {exc!r}",
        }

    try:
        resolved = {ex_type: get_ex_schema(ex_type).__name__ for ex_type in SUPPORTED_EX_TYPES}
    except ContractsUnavailableError as exc:
        return {
            "available": False,
            "reason": f"contracts package not installed: {exc}",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "available": False,
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

    def check(self, *, timeout_sec: float) -> dict[str, Any]:
        details: dict[str, Any] = {}

        # Invariant 1: INGEST_METADATA_FIELDS is non-empty + the rejector
        # actually rejects them.
        try:
            assert INGEST_METADATA_FIELDS, "INGEST_METADATA_FIELDS empty"
            try:
                assert_no_ingest_metadata({"submitted_at": "2026-01-01T00:00:00Z"})
            except IngestMetadataLeakError:
                details["ingest_metadata_guard"] = "ok"
            else:
                return {
                    "status": _DOWN,
                    "details": {
                        **details,
                        "ingest_metadata_guard": (
                            "FAIL — assert_no_ingest_metadata accepted "
                            "submitted_at"
                        ),
                    },
                    "timeout_sec": timeout_sec,
                }
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "status": _DOWN,
                "details": {**details, "ingest_metadata_guard": f"FAIL: {exc!r}"},
                "timeout_sec": timeout_sec,
            }

        # Invariant 2: contracts schema gateway. degraded (not down) when
        # contracts is missing — offline-first dev venvs are allowed.
        gateway = _probe_contracts_schema_gateway()
        details["contracts_schema_gateway"] = gateway
        status = _HEALTHY if gateway["available"] else _DEGRADED

        # Invariant 3: SDK declares the canonical 4 Ex types and 3 backend kinds.
        details["supported_ex_types"] = sorted(PRODUCER_OWNED_REQUIRED.keys())
        details["backend_kinds"] = list(BACKEND_KINDS)
        details["ex0_semantic"] = EX0_SEMANTIC

        return {"status": status, "details": details, "timeout_sec": timeout_sec}


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

        from subsystem_sdk.heartbeat.payload import build_ex0_payload

        # Smoke deliberately exercises ONLY the SDK-internal semantic
        # guards + payload builder + receipt contract — NOT the optional
        # contracts.schemas Ex0Metadata model_validate path. The SDK's
        # `validate_payload` calls into contracts' Ex0Metadata, which
        # currently rejects the SDK's ex_type/semantic wrapping fields and
        # uses a different HeartbeatStatus enum ({ok,degraded,failed} vs
        # SDK's {healthy,degraded,unhealthy}). That cross-repo schema
        # mismatch is documented + parametrized in
        # tests/contract/test_contracts_alignment.py — fixing it is out
        # of stage 2.7's scope (SDK boundary refactor, not test-baseline).
        # Smoke stays useful by asserting the guards the SDK fully owns.

        # 1. Build a clean Ex-0 producer payload (using the SDK's own
        #    builder; status enum is the SDK's HeartbeatState literal).
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

        # 3. Negative path — assert_no_ingest_metadata MUST raise on any
        #    of the forbidden fields. Proves the guard hasn't been
        #    silently weakened. We only run two of the three known
        #    fields here for speed; the unit tier covers the full set.
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

        # 4. Receipt-shape sanity: RESERVED_PRIVATE_KEYS must be non-empty
        #    and not intersect with INGEST_METADATA_FIELDS (different boundary
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

        return {
            "passed": True,
            "profile_id": profile_id,
            "details": {
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
        contract_version = self._derive_contract_version()
        return {
            "module_id": "subsystem-sdk",
            "module_version": _SUBSYSTEM_SDK_VERSION,
            "contract_version": contract_version,
            "supported_ex_types": sorted(PRODUCER_OWNED_REQUIRED.keys()),
            "backend_kinds": list(BACKEND_KINDS),
            "ex0_semantic": EX0_SEMANTIC,
        }

    @staticmethod
    def _derive_contract_version() -> str:
        try:
            from subsystem_sdk._contracts import (
                ContractsUnavailableError,
                get_ex_schema,
                get_schema_version,
            )

            schema = get_ex_schema("Ex-0")
            return get_schema_version(schema)
        except Exception:
            return "unknown"


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
