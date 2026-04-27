import json
import sys
import types
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from subsystem_sdk.backends import PgSubmitBackend, SubmitBackendConfig
from subsystem_sdk.submit import SubmitClient
from subsystem_sdk.validate import registry


class Ex1CandidatePayload(BaseModel):
    SCHEMA_VERSION: ClassVar[str] = "v-ex1-lite-pg"
    model_config = ConfigDict(extra="forbid")

    ex_type: Literal["Ex-1"] = "Ex-1"
    subsystem_id: str
    entity_id: str


class FakeCursor:
    def __init__(self, row: Any = (42,)) -> None:
        self.row = row
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.execute_calls.append((sql, params))

    def fetchone(self) -> Any:
        return self.row

    def close(self) -> None:
        self.closed = True


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


class BlockingLookup:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def lookup(self, refs: Iterable[str]) -> Mapping[str, bool]:
        refs_tuple = tuple(refs)
        self.calls.append(refs_tuple)
        return {ref: False for ref in refs_tuple}


def _install_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("contracts")
    module.EX_PAYLOAD_SCHEMAS = {"Ex-1": Ex1CandidatePayload}
    monkeypatch.setitem(sys.modules, "contracts", module)
    monkeypatch.setattr(registry, "_DEFAULT_REGISTRY", registry.ValidatorRegistry())


def test_pg_submit_backend_inserts_commits_and_maps_queue_id() -> None:
    cursor = FakeCursor(row={"pg_queue_id": "queue-42"})
    connection = FakeConnection(cursor)
    config = SubmitBackendConfig(
        backend_kind="lite_pg",
        dsn=None,
        queue_table="private_queue_table",
    )
    backend = PgSubmitBackend(config, connection_factory=lambda received: connection)

    receipt = backend.submit({"ex_type": "Ex-2", "subsystem_id": "subsystem-a"})

    assert len(cursor.execute_calls) == 1
    sql, params = cursor.execute_calls[0]
    assert 'insert into "private_queue_table"' in sql
    assert json.loads(params[0]) == {
        "ex_type": "Ex-2",
        "subsystem_id": "subsystem-a",
    }
    assert connection.commits == 1
    assert cursor.closed is True
    assert connection.closed is True
    assert receipt == {
        "accepted": True,
        "transport_ref": "queue-42",
        "warnings": (),
        "errors": (),
    }
    assert "pg_queue_id" not in receipt
    assert "sql" not in receipt
    assert "private_queue_table" not in receipt.values()


def test_pg_submit_backend_uses_injected_factory_without_psycopg() -> None:
    cursor = FakeCursor(row=(7,))
    connection = FakeConnection(cursor)
    config = SubmitBackendConfig(backend_kind="lite_pg")
    calls: list[SubmitBackendConfig] = []

    def factory(received: SubmitBackendConfig) -> FakeConnection:
        calls.append(received)
        return connection

    receipt = PgSubmitBackend(config, connection_factory=factory).submit(
        {"ex_type": "Ex-1"}
    )

    assert calls == [config]
    assert receipt["transport_ref"] == "7"


def test_pg_submit_backend_rejects_unsafe_queue_table_identifier() -> None:
    cursor = FakeCursor(row=(7,))
    connection = FakeConnection(cursor)
    config = SubmitBackendConfig(
        backend_kind="lite_pg",
        queue_table='subsystem_submit_queue; drop table "contracts"',
    )

    with pytest.raises(ValueError, match="queue_table"):
        PgSubmitBackend(config, connection_factory=lambda received: connection)

    assert cursor.execute_calls == []
    assert connection.commits == 0
    assert connection.closed is False


def test_pg_submit_backend_requires_lite_pg_config() -> None:
    with pytest.raises(ValueError, match="lite_pg"):
        PgSubmitBackend(SubmitBackendConfig(backend_kind="mock"))


def test_pg_submit_client_block_preflight_does_not_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_contracts(monkeypatch)
    cursor = FakeCursor(row={"pg_queue_id": "queue-42"})
    connection = FakeConnection(cursor)
    factory_calls: list[SubmitBackendConfig] = []

    def factory(received: SubmitBackendConfig) -> FakeConnection:
        factory_calls.append(received)
        return connection

    backend = PgSubmitBackend(
        SubmitBackendConfig(backend_kind="lite_pg"),
        connection_factory=factory,
    )
    lookup = BlockingLookup()
    payload = {
        "ex_type": "Ex-1",
        "subsystem_id": "subsystem-a",
        "produced_at": "2026-04-27T00:00:00Z",
        "entity_id": "missing-entity",
    }

    receipt = SubmitClient(
        backend,
        entity_lookup=lookup,
        preflight_policy="block",
    ).submit(payload)

    assert lookup.calls == [("missing-entity",)]
    assert receipt.accepted is False
    assert receipt.backend_kind == "lite_pg"
    assert receipt.validator_version == "v-ex1-lite-pg"
    assert receipt.errors == (
        "entity preflight blocked unresolved reference(s): missing-entity",
    )
    assert factory_calls == []
    assert cursor.execute_calls == []
    assert connection.commits == 0
    assert connection.closed is False
