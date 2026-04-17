"""Lite PostgreSQL submit backend adapter."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from subsystem_sdk.backends.config import SubmitBackendConfig
from subsystem_sdk.submit.receipt import BackendKind

_DEFAULT_QUEUE_TABLE = "subsystem_submit_queue"


class PgSubmitBackend:
    """Lite PG adapter that maps queue ids to public transport refs."""

    backend_kind: BackendKind = "lite_pg"

    def __init__(
        self,
        config: SubmitBackendConfig,
        connection_factory: Callable[[SubmitBackendConfig], Any] | None = None,
    ) -> None:
        if config.backend_kind != self.backend_kind:
            raise ValueError("PgSubmitBackend requires backend_kind='lite_pg'")
        self._config = config
        self._connection_factory = connection_factory

    @property
    def config(self) -> SubmitBackendConfig:
        return self._config

    def _connect(self) -> Any:
        if self._connection_factory is not None:
            return self._connection_factory(self._config)

        if self._config.dsn is None:
            raise ValueError("PgSubmitBackend requires dsn without connection_factory")

        import psycopg  # type: ignore[import-not-found]

        return psycopg.connect(
            self._config.dsn,
            connect_timeout=self._config.connect_timeout_ms / 1000,
        )

    def submit(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        connection = self._connect()
        try:
            queue_id = self._insert_payload(connection, payload)
            commit = getattr(connection, "commit", None)
            if callable(commit):
                commit()
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

        return {
            "accepted": True,
            "transport_ref": str(queue_id),
            "warnings": (),
            "errors": (),
        }

    def _insert_payload(self, connection: Any, payload: Mapping[str, Any]) -> Any:
        cursor_owner = connection.cursor()
        if hasattr(cursor_owner, "__enter__"):
            with cursor_owner as cursor:
                return self._execute_insert(cursor, payload)

        try:
            return self._execute_insert(cursor_owner, payload)
        finally:
            close = getattr(cursor_owner, "close", None)
            if callable(close):
                close()

    def _execute_insert(self, cursor: Any, payload: Mapping[str, Any]) -> Any:
        queue_table = self._config.queue_table or _DEFAULT_QUEUE_TABLE
        sql = f"insert into {queue_table} (payload) values (%s) returning id"
        payload_json = json.dumps(dict(payload), sort_keys=True)

        cursor.execute(sql, (payload_json,))
        row = cursor.fetchone()
        return _extract_queue_id(row)


def _extract_queue_id(row: Any) -> Any:
    if row is None:
        raise RuntimeError("PG insert did not return a queue id")

    if isinstance(row, Mapping):
        for key in ("id", "queue_id", "pg_queue_id"):
            if key in row:
                return row[key]
        raise RuntimeError("PG insert row did not include a queue id")

    try:
        return row[0]
    except (IndexError, KeyError, TypeError) as exc:
        raise RuntimeError("PG insert row did not include a queue id") from exc
