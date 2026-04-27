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

CONTROLLED_CYCLE_ID = "cycle:p4-controlled-bridge:001"
CONTROLLED_SUBSYSTEM_ID = "p4-controlled-subsystem"
CONTROLLED_EVIDENCE_REF = "controlled-bridge-fixture#body:0-64"


class RecordingPgFactory:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.connection_attempts = 0
        self.commits = 0
        self.closed_connections = 0

    def __call__(self, _config: SubmitBackendConfig) -> "RecordingConnection":
        self.connection_attempts += 1
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
    assert pg_factory.connection_attempts == 4
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

    assert queued_payloads[0]["producer_context"] == {
        "event_anchor_policy": "event-entity-first"
    }
    assert queued_payloads[1]["producer_context"] == {
        "event_anchor_policy": "event-entity-first"
    }
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


def test_default_production_live_lookup_blocks_unresolved_ex2_before_pg_dispatch() -> None:
    """Production default uses entity-registry lookup and blocks before PG insert.

    This intentionally uses the SDK PG adapter with an injected connection
    factory, not a live PostgreSQL server.
    """

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
    missing_ref = "ENT_STOCK_000000.SZ"
    payload = _ex2_payload(stock_id, event_id) | {
        "signal_id": "signal:p4-controlled:unresolved-before-pg",
        "affected_entities": [stock_id, missing_ref],
    }

    receipt = submit_client.submit(payload)

    assert receipt.accepted is False
    assert receipt.backend_kind == "lite_pg"
    assert receipt.transport_ref is None
    assert receipt.errors == (
        f"entity preflight blocked unresolved reference(s): {missing_ref}",
    )
    assert (
        f"entity preflight found unresolved reference(s): {missing_ref}"
        in receipt.warnings
    )
    assert pg_factory.connection_attempts == 0
    assert pg_factory.records == []
    assert pg_factory.commits == 0
    assert pg_factory.closed_connections == 0


def test_controlled_bridge_projection_scaffold_preserves_ids_and_evidence_refs() -> None:
    """SDK-local scaffold for downstream read-only projection inputs.

    The scaffold projects queued Ex payloads into local dictionaries to prove
    that a future bridge can carry validated entity IDs and evidence refs when
    supplied an explicit cycle context. It does not treat producer_context as a
    public bridge contract, and it does not call graph-engine, reasoner-runtime,
    frontend write APIs, news, or Polymarket.
    """

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

    receipts = [
        submit_client.submit(_ex1_payload(stock_id, event_id)),
        submit_client.submit(_ex2_payload(stock_id, event_id)),
        submit_client.submit(_ex3_payload(stock_id, event_id)),
    ]

    assert [receipt.accepted for receipt in receipts] == [True, True, True]
    queued_payloads = [record["payload"] for record in pg_factory.records]
    artifacts = _controlled_bridge_projection_artifacts(
        queued_payloads,
        cycle_id=CONTROLLED_CYCLE_ID,
        event_entity_id=event_id,
    )

    assert artifacts["graph"] == {
        "artifact_kind": "sdk-local-projection.candidate-graph-delta",
        "cycle_id": CONTROLLED_CYCLE_ID,
        "delta_id": "delta:p4-controlled:event-impacts-stock",
        "source_node": event_id,
        "target_node": stock_id,
        "relation_type": "event_impacts_entity",
        "evidence_refs": [CONTROLLED_EVIDENCE_REF],
    }
    assert artifacts["reasoner"] == {
        "artifact_kind": "sdk-local-projection.reasoner-context-input",
        "cycle_id": CONTROLLED_CYCLE_ID,
        "input_signal_id": "signal:p4-controlled:contract-award",
        "entity_ids": [stock_id],
        "event_entity_id": event_id,
        "evidence_refs": [CONTROLLED_EVIDENCE_REF],
        "llm_mode": "disabled-controlled-scaffold",
    }
    assert artifacts["frontend_api"] == {
        "artifact_kind": "sdk-local-projection.frontend-read-model-input",
        "cycle_id": CONTROLLED_CYCLE_ID,
        "read_only": True,
        "entity_cards": [
            {
                "canonical_entity_id": stock_id,
                "evidence_refs": [CONTROLLED_EVIDENCE_REF],
            },
            {
                "canonical_entity_id": event_id,
                "evidence_refs": [CONTROLLED_EVIDENCE_REF],
            },
        ],
    }

    serialized = json.dumps(artifacts, sort_keys=True).lower()
    for forbidden in (
        "polymarket",
        "external-news",
        "frontend-write",
        "mutation_endpoint",
        "write_endpoint",
        "post_endpoint",
    ):
        assert forbidden not in serialized


def test_controlled_bridge_projection_rejects_mismatched_event_identity() -> None:
    stock_id, event_id = _configure_anchored_registry()
    payloads = [
        _ex1_payload(stock_id, event_id),
        _ex2_payload(stock_id, event_id),
        _ex3_payload(stock_id, event_id) | {"source_node": "ENT_EVENT_WRONG"},
    ]

    with pytest.raises(ValueError, match="Ex-3 source_node must match explicit event"):
        _controlled_bridge_projection_artifacts(
            payloads,
            cycle_id=CONTROLLED_CYCLE_ID,
            event_entity_id=event_id,
        )


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
        namespace="controlled-bridge-fixture",
        event_key="cycle-001#contract-award",
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
        "subsystem_id": CONTROLLED_SUBSYSTEM_ID,
        "fact_id": "fact:p4-controlled:contract-award",
        "entity_id": stock_id,
        "fact_type": "controlled_contract_award",
        "fact_content": {"summary": "Controlled contract award event."},
        "confidence": 0.94,
        "source_reference": {"fixture": "controlled-bridge-fixture"},
        "extracted_at": _timestamp(),
        "evidence": [CONTROLLED_EVIDENCE_REF],
        "producer_context": {"event_anchor_policy": "event-entity-first"},
        "produced_at": _timestamp(),
    }


def _ex2_payload(stock_id: str, event_id: str) -> dict[str, Any]:
    return {
        "ex_type": "Ex-2",
        "subsystem_id": CONTROLLED_SUBSYSTEM_ID,
        "signal_id": "signal:p4-controlled:contract-award",
        "signal_type": "event_impact",
        "direction": "bullish",
        "magnitude": 0.7,
        "affected_entities": [stock_id],
        "affected_sectors": [],
        "time_horizon": "short",
        "evidence": [CONTROLLED_EVIDENCE_REF],
        "confidence": 0.9,
        "producer_context": {"event_anchor_policy": "event-entity-first"},
        "produced_at": _timestamp(),
    }


def _ex3_payload(stock_id: str, event_id: str) -> dict[str, Any]:
    return {
        "ex_type": "Ex-3",
        "subsystem_id": CONTROLLED_SUBSYSTEM_ID,
        "delta_id": "delta:p4-controlled:event-impacts-stock",
        "delta_type": "add_edge",
        "source_node": event_id,
        "target_node": stock_id,
        "relation_type": "event_impacts_entity",
        "properties": {"direction": "bullish", "magnitude": 0.7},
        "evidence": [CONTROLLED_EVIDENCE_REF],
        "producer_context": {"anchor_policy": "event-entity-first"},
        "produced_at": _timestamp(),
    }


def _controlled_bridge_projection_artifacts(
    queued_payloads: list[dict[str, Any]],
    *,
    cycle_id: str,
    event_entity_id: str,
) -> dict[str, Any]:
    fact, signal, delta = queued_payloads
    _assert_controlled_bridge_identity(
        fact=fact,
        signal=signal,
        delta=delta,
        event_entity_id=event_entity_id,
    )
    evidence_refs = _unique_refs(
        [
            *(fact.get("evidence") or []),
            *signal["evidence"],
            *delta["evidence"],
        ]
    )

    return {
        "graph": {
            "artifact_kind": "sdk-local-projection.candidate-graph-delta",
            "cycle_id": cycle_id,
            "delta_id": delta["delta_id"],
            "source_node": delta["source_node"],
            "target_node": delta["target_node"],
            "relation_type": delta["relation_type"],
            "evidence_refs": list(delta["evidence"]),
        },
        "reasoner": {
            "artifact_kind": "sdk-local-projection.reasoner-context-input",
            "cycle_id": cycle_id,
            "input_signal_id": signal["signal_id"],
            "entity_ids": list(signal["affected_entities"]),
            "event_entity_id": event_entity_id,
            "evidence_refs": evidence_refs,
            "llm_mode": "disabled-controlled-scaffold",
        },
        "frontend_api": {
            "artifact_kind": "sdk-local-projection.frontend-read-model-input",
            "cycle_id": cycle_id,
            "read_only": True,
            "entity_cards": [
                {
                    "canonical_entity_id": fact["entity_id"],
                    "evidence_refs": list(fact.get("evidence") or []),
                },
                {
                    "canonical_entity_id": event_entity_id,
                    "evidence_refs": evidence_refs,
                },
            ],
        },
    }


def _assert_controlled_bridge_identity(
    *,
    fact: dict[str, Any],
    signal: dict[str, Any],
    delta: dict[str, Any],
    event_entity_id: str,
) -> None:
    entity_id = fact["entity_id"]
    affected_entities = signal["affected_entities"]
    if affected_entities != [entity_id]:
        raise ValueError("Ex-2 affected_entities must match Ex-1 entity_id")
    if delta["source_node"] != event_entity_id:
        raise ValueError("Ex-3 source_node must match explicit event entity id")
    if delta["target_node"] != entity_id:
        raise ValueError("Ex-3 target_node must match Ex-1 entity_id")


def _unique_refs(refs: list[str]) -> list[str]:
    return list(dict.fromkeys(refs))
