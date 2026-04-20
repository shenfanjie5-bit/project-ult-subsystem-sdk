import sys
import types
from datetime import UTC, datetime, timezone, timedelta
from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.heartbeat import (
    HeartbeatStatus,
    build_ex0_payload,
)
from subsystem_sdk.validate import EX0_SEMANTIC, validate_payload


class Ex0HeartbeatPayload(BaseModel):
    """Fake contracts schema for unit-tier validate_payload tests.

    Mirrors ``contracts.schemas.Ex0Metadata`` (real published shape):
    - ``extra='forbid'`` — same strictness as the real schema
    - ``status`` uses the contracts wire enum {ok, degraded, failed}
      (NOT the SDK-side {healthy, degraded, unhealthy} HeartbeatState)
    - No ``ex_type`` / ``semantic`` envelope fields — those are stripped
      by ``validate_payload._strip_sdk_envelope`` before model_validate
      (codex stage-2.7 P1 fix). If this fake regrows envelope fields,
      it stops mirroring real contracts and starts hiding bugs.

    Real-contracts integration is in
    ``tests/contract/test_contracts_alignment.py`` and
    ``tests/fixtures/test_contract_roundtrip_real.py``.
    """

    SCHEMA_VERSION: ClassVar[str] = "v-ex0-heartbeat"
    model_config = ConfigDict(extra="forbid")

    subsystem_id: str
    version: str
    heartbeat_at: datetime
    # Contracts wire enum — kept in sync with
    # ``contracts.core.types.HeartbeatStatus`` ({ok, degraded, failed}).
    status: Literal["ok", "degraded", "failed"]
    last_output_at: datetime | None = None
    pending_count: int


def _install_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {"Ex-0": Ex0HeartbeatPayload}
    monkeypatch.setitem(sys.modules, "contracts", module)


def test_build_ex0_payload_uses_fixed_ex0_semantic() -> None:
    heartbeat_at = datetime(2026, 4, 17, 12, 30, 15, tzinfo=UTC)
    last_output_at = datetime(2026, 4, 17, 12, 29, 10, tzinfo=UTC)

    payload = build_ex0_payload(
        "subsystem-demo",
        "0.1.0",
        HeartbeatStatus(
            status="healthy",
            last_output_at=last_output_at,
            pending_count=4,
        ),
        heartbeat_at=heartbeat_at,
    )

    # Wire payload: status mapped to contracts' HeartbeatStatus enum
    # ({ok,degraded,failed}) — codex stage-2.7 P1 fix. SDK envelope
    # fields (ex_type, semantic) stay in the SDK-side dict for routing
    # but are stripped by validate_payload before contracts model_validate.
    assert payload == {
        "ex_type": "Ex-0",
        "semantic": EX0_SEMANTIC,
        "subsystem_id": "subsystem-demo",
        "version": "0.1.0",
        "heartbeat_at": "2026-04-17T12:30:15Z",
        "status": "ok",  # SDK "healthy" -> contracts "ok" wire enum
        "last_output_at": "2026-04-17T12:29:10Z",
        "pending_count": 4,
    }


def test_build_ex0_payload_omits_ingest_metadata_fields() -> None:
    payload = build_ex0_payload(
        "subsystem-demo",
        "0.1.0",
        "healthy",
        heartbeat_at=datetime(2026, 4, 17, tzinfo=UTC),
    )

    assert "submitted_at" not in payload
    assert "ingest_seq" not in payload
    assert "layer_b_receipt_id" not in payload


def test_build_ex0_payload_accepts_status_mapping_without_business_fields() -> None:
    heartbeat_at = datetime(2026, 4, 17, 8, 0, 0, tzinfo=UTC)
    last_output_at = datetime(2026, 4, 17, 15, 30, 0, tzinfo=timezone(timedelta(hours=8)))

    payload = build_ex0_payload(
        "subsystem-demo",
        "0.1.0",
        {
            "status": "degraded",
            "last_output_at": last_output_at,
            "pending_count": 2,
        },
        heartbeat_at=heartbeat_at,
    )

    assert payload["status"] == "degraded"
    assert payload["last_output_at"] == "2026-04-17T07:30:00Z"
    assert payload["pending_count"] == 2


def test_build_ex0_payload_can_pass_validate_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_contracts(monkeypatch)
    payload = build_ex0_payload(
        "subsystem-demo",
        "0.1.0",
        HeartbeatStatus(status="healthy"),
        heartbeat_at=datetime(2026, 4, 17, tzinfo=UTC),
    )

    result = validate_payload(payload)

    assert result.is_valid is True
    assert result.ex_type == "Ex-0"
    assert result.schema_version == "v-ex0-heartbeat"


@pytest.mark.parametrize("status", ("fact", "signal", "graph_delta", "business_event"))
def test_build_ex0_payload_rejects_non_heartbeat_status(status: str) -> None:
    with pytest.raises(ValueError, match="heartbeat status"):
        build_ex0_payload("subsystem-demo", "0.1.0", status)


def test_build_ex0_payload_rejects_negative_pending_count() -> None:
    with pytest.raises(ValueError, match="pending_count"):
        build_ex0_payload(
            "subsystem-demo",
            "0.1.0",
            {"status": "healthy", "pending_count": -1},
        )


@pytest.mark.parametrize(
    "field_name", ("fact", "signal", "graph_delta", "business_event", "headline")
)
def test_build_ex0_payload_rejects_business_fields(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        build_ex0_payload(
            "subsystem-demo",
            "0.1.0",
            {"status": "healthy", field_name: "business-data"},
        )


def test_heartbeat_status_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="heartbeat status"):
        HeartbeatStatus(status="ok")  # type: ignore[arg-type]


def test_heartbeat_status_rejects_non_datetime_last_output() -> None:
    with pytest.raises(TypeError, match="last_output_at"):
        HeartbeatStatus(status="healthy", last_output_at="2026-04-17")  # type: ignore[arg-type]
