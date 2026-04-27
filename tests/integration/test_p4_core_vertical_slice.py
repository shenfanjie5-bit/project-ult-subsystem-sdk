from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from subsystem_sdk.backends import (
    PgSubmitBackend,
    SubmitBackendConfig,
    SubmitBackendHeartbeatAdapter,
)
from subsystem_sdk.base import BaseSubsystemContext, SubsystemRegistrationSpec
from subsystem_sdk.heartbeat import HeartbeatClient
from subsystem_sdk.submit import SubmitClient

contracts_schemas = pytest.importorskip("contracts.schemas")
entity_registry = pytest.importorskip("entity_registry")


class RecordingPgFactory:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.commits = 0
        self.closed_connections = 0

    def __call__(self, _config: SubmitBackendConfig) -> "RecordingConnection":
        return RecordingConnection(self)

    def insert(self, sql: str, params: tuple[Any, ...]) -> str:
        queue_id = f"queue-{len(self.records) + 1}"
        self.records.append(
            {
                "queue_id": queue_id,
                "sql": sql,
                "payload": json.loads(params[0]),
            }
        )
        return queue_id


class RecordingConnection:
    def __init__(self, factory: RecordingPgFactory) -> None:
        self._factory = factory

    def cursor(self) -> "RecordingCursor":
        return RecordingCursor(self._factory)

    def commit(self) -> None:
        self._factory.commits += 1

    def close(self) -> None:
        self._factory.closed_connections += 1


class RecordingCursor:
    def __init__(self, factory: RecordingPgFactory) -> None:
        self._factory = factory
        self._queue_id: str | None = None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self._queue_id = self._factory.insert(sql, params)

    def fetchone(self) -> Mapping[str, str]:
        assert self._queue_id is not None
        return {"pg_queue_id": self._queue_id}

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_entity_registry() -> None:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def test_lite_pg_vertical_slice_queues_anchored_candidates_and_heartbeat() -> None:
    stock_id, event_id = _configure_anchored_registry()
    pg_factory = RecordingPgFactory()
    backend = PgSubmitBackend(
        SubmitBackendConfig(
            backend_kind="lite_pg",
            queue_table="subsystem_submit_queue",
        ),
        connection_factory=pg_factory,
    )
    submit_client = SubmitClient(
        backend,
        entity_preflight_profile="production",
    )

    fact_receipt = submit_client.submit(_ex1_payload(stock_id, event_id))
    signal_receipt = submit_client.submit(_ex2_payload(stock_id, event_id))
    graph_receipt = submit_client.submit(_ex3_payload(stock_id, event_id))

    context = BaseSubsystemContext(
        registration=SubsystemRegistrationSpec(
            subsystem_id="p4-controlled-subsystem",
            version="0.1.0",
            domain="controlled-p4",
            supported_ex_types=["Ex-0", "Ex-1", "Ex-2", "Ex-3"],
            owner="backend-e",
            heartbeat_policy_ref="controlled:manual",
        ),
        submit_client=submit_client,
        heartbeat_client=HeartbeatClient(SubmitBackendHeartbeatAdapter(backend)),
    )
    heartbeat_receipt = context.send_heartbeat(
        {"status": "healthy", "pending_count": 0}
    )

    assert [receipt.accepted for receipt in (
        fact_receipt,
        signal_receipt,
        graph_receipt,
        heartbeat_receipt,
    )] == [True, True, True, True]
    assert [receipt.transport_ref for receipt in (
        fact_receipt,
        signal_receipt,
        graph_receipt,
        heartbeat_receipt,
    )] == ["queue-1", "queue-2", "queue-3", "queue-4"]
    assert pg_factory.commits == 4
    assert pg_factory.closed_connections == 4

    queued_payloads = [record["payload"] for record in pg_factory.records]
    assert [record["queue_id"] for record in pg_factory.records] == [
        "queue-1",
        "queue-2",
        "queue-3",
        "queue-4",
    ]
    assert all(
        'insert into "subsystem_submit_queue"' in record["sql"]
        for record in pg_factory.records
    )
    assert all(
        "ex_type" not in payload and "produced_at" not in payload
        for payload in queued_payloads
    )

    contracts_schemas.Ex1CandidateFact.model_validate(queued_payloads[0])
    contracts_schemas.Ex2CandidateSignal.model_validate(queued_payloads[1])
    contracts_schemas.Ex3CandidateGraphDelta.model_validate(queued_payloads[2])
    contracts_schemas.Ex0Metadata.model_validate(queued_payloads[3])

    assert queued_payloads[0]["producer_context"]["event_entity_id"] == event_id
    assert queued_payloads[1]["producer_context"]["event_entity_id"] == event_id
    assert queued_payloads[2]["source_node"] == event_id
    assert queued_payloads[2]["target_node"] == stock_id

    rejected = submit_client.submit(
        _ex3_payload(stock_id, "ENT_EVENT_CONTROLLED_MISSING")
    )
    assert rejected.accepted is False
    assert rejected.transport_ref is None
    assert rejected.errors == (
        "entity preflight blocked unresolved reference(s): "
        "ENT_EVENT_CONTROLLED_MISSING",
    )
    assert len(pg_factory.records) == 4


def _configure_anchored_registry() -> tuple[str, str]:
    from entity_registry.core import CanonicalEntity, EntityStatus, EntityType
    from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository

    entity_repo = InMemoryEntityRepository()
    stock_id = "ENT_STOCK_600519.SH"
    entity_repo.save(
        CanonicalEntity(
            canonical_entity_id=stock_id,
            entity_type=EntityType.STOCK,
            display_name="Kweichow Moutai",
            status=EntityStatus.ACTIVE,
            anchor_code="600519.SH",
        )
    )
    event = entity_registry.anchor_event_entity(
        entity_repo,
        namespace="controlled-news",
        event_key="article-001#contract-award",
        display_name="Controlled contract award event",
    )
    entity_registry.configure_default_repositories(
        entity_repo,
        InMemoryAliasRepository(),
    )
    return stock_id, event.canonical_entity_id


def _timestamp() -> str:
    return datetime(2026, 4, 28, 0, 0, tzinfo=UTC).isoformat()


def _ex1_payload(stock_id: str, event_id: str) -> dict[str, Any]:
    return {
        "ex_type": "Ex-1",
        "subsystem_id": "p4-controlled-subsystem",
        "fact_id": "fact:p4-controlled:contract-award",
        "entity_id": stock_id,
        "fact_type": "controlled_contract_award",
        "fact_content": {"summary": "Controlled contract award event."},
        "confidence": 0.94,
        "source_reference": {"fixture": "controlled-news"},
        "extracted_at": _timestamp(),
        "evidence": ["controlled-news#body:0-64"],
        "producer_context": {"event_entity_id": event_id},
        "produced_at": _timestamp(),
    }


def _ex2_payload(stock_id: str, event_id: str) -> dict[str, Any]:
    return {
        "ex_type": "Ex-2",
        "subsystem_id": "p4-controlled-subsystem",
        "signal_id": "signal:p4-controlled:contract-award",
        "signal_type": "event_impact",
        "direction": "bullish",
        "magnitude": 0.7,
        "affected_entities": [stock_id],
        "affected_sectors": [],
        "time_horizon": "short",
        "evidence": ["controlled-news#body:0-64"],
        "confidence": 0.9,
        "producer_context": {"event_entity_id": event_id},
        "produced_at": _timestamp(),
    }


def _ex3_payload(stock_id: str, event_id: str) -> dict[str, Any]:
    return {
        "ex_type": "Ex-3",
        "subsystem_id": "p4-controlled-subsystem",
        "delta_id": "delta:p4-controlled:event-impacts-stock",
        "delta_type": "add_edge",
        "source_node": event_id,
        "target_node": stock_id,
        "relation_type": "event_impacts_entity",
        "properties": {"direction": "bullish", "magnitude": 0.7},
        "evidence": ["controlled-news#body:0-64"],
        "producer_context": {"anchor_policy": "event-entity-first"},
        "produced_at": _timestamp(),
    }
