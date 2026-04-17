import json
import sys
import types
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.backends import (
    PgSubmitBackend,
    SubmitBackendConfig,
    SubmitBackendHeartbeatAdapter,
)
from subsystem_sdk.base import BaseSubsystemContext, SubsystemRegistrationSpec
from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.submit import SubmitClient
from subsystem_sdk.validate import EX0_SEMANTIC


class Ex0HeartbeatPayload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex0-heartbeat"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-0"] = "Ex-0"
    semantic: Literal["metadata_or_heartbeat"] = EX0_SEMANTIC
    subsystem_id: str
    version: str
    heartbeat_at: str
    status: str
    last_output_at: str | None = None
    pending_count: int = 0


class FakeCursor:
    def __init__(self, row: Any) -> None:
        self.row = row
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.execute_calls.append((sql, params))

    def fetchone(self) -> Any:
        return self.row

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor
        self.commits = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


def _install_ex0_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {"Ex-0": Ex0HeartbeatPayload}
    monkeypatch.setitem(sys.modules, "contracts", module)


def test_lite_pg_heartbeat_adapter_sends_context_ex0_through_submit_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ex0_contracts(monkeypatch)
    cursor = FakeCursor(row={"pg_queue_id": "heartbeat-42"})
    connection = FakeConnection(cursor)
    config = SubmitBackendConfig(
        backend_kind="lite_pg",
        dsn=None,
        queue_table="subsystem_submit_queue",
    )
    submit_backend = PgSubmitBackend(
        config,
        connection_factory=lambda received: connection,
    )
    context = BaseSubsystemContext(
        registration=SubsystemRegistrationSpec(
            subsystem_id="subsystem-demo",
            version="0.1.0",
            domain="demo",
            supported_ex_types=["Ex-0"],
            owner="sdk",
            heartbeat_policy_ref="default",
        ),
        submit_client=SubmitClient(submit_backend),
        heartbeat_client=HeartbeatClient(
            SubmitBackendHeartbeatAdapter(submit_backend),
        ),
    )

    receipt = context.send_heartbeat({"status": "healthy", "pending_count": 2})

    assert receipt.accepted is True
    assert receipt.backend_kind == "lite_pg"
    assert receipt.transport_ref == "heartbeat-42"
    assert receipt.validator_version == "v-ex0-heartbeat"
    assert receipt.errors == ()
    assert connection.commits == 1
    assert connection.closed is True

    sql, params = cursor.execute_calls[0]
    payload = json.loads(params[0])
    assert 'insert into "subsystem_submit_queue"' in sql
    assert payload["ex_type"] == "Ex-0"
    assert payload["semantic"] == EX0_SEMANTIC
    assert payload["subsystem_id"] == "subsystem-demo"
    assert payload["version"] == "0.1.0"
    assert payload["status"] == "healthy"
    assert payload["pending_count"] == 2
    assert "pg_queue_id" not in receipt.model_dump()
