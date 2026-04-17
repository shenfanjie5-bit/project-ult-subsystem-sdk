from typing import Any

import pytest

from subsystem_sdk.backends import PgSubmitBackend, SubmitBackendConfig


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
    assert "private_queue_table" in cursor.execute_calls[0][0]
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


def test_pg_submit_backend_requires_lite_pg_config() -> None:
    with pytest.raises(ValueError, match="lite_pg"):
        PgSubmitBackend(SubmitBackendConfig(backend_kind="mock"))
