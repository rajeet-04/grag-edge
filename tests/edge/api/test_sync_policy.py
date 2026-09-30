import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.runtime import EdgeRuntime
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox
from app.edge.sync.workflow import PolicyWorkflow


class Embeddings:
    async def embed_with_context(self, text, task_type):
        return [0.1, 0.2, 0.3, 0.4]

    async def embed_text(self, text):
        return [0.1, 0.2, 0.3, 0.4]

    async def close(self):
        pass


@pytest.fixture
def sync_client(tmp_path: Path, monkeypatch):
    import app.edge.runtime as runtime_module
    import app.database.neo4j_client as neo4j_module

    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
    store.open()
    runtime = EdgeRuntime(store=store, embedding_service=Embeddings(), state_path=tmp_path / "state.db")
    monkeypatch.setattr(runtime_module, "EdgeRuntime", lambda: runtime)

    class Neo4j:
        async def verify_connectivity(self):
            return False

        async def close(self):
            pass

    monkeypatch.setattr(neo4j_module, "get_neo4j_client", lambda: Neo4j())
    from app.main import app

    with TestClient(app) as client:
        yield client, runtime


def test_privacy_beats_auto_and_memory_decision_is_inspectable(sync_client):
    client, runtime = sync_client
    response = client.post("/api/v1/edge/memories", json={
        "content": "critical restricted incident", "memory_type": "incident", "importance": "critical",
        "sensitivity": "restricted", "confidence": 0.99, "sync_policy": "auto",
    })
    assert response.status_code == 201
    record = response.json()
    assert record["requested_sync_policy"] == "auto"
    assert record["sync_policy"] == "local_only"
    assert record["sync_state"] == "LOCAL_ONLY"
    assert "privacy_restricted" in record["sync_reason_codes"]
    assert runtime.outbox.pending(10) == []


def test_approval_queues_current_revision_once_and_emits_once(sync_client):
    client, runtime = sync_client
    response = client.post("/api/v1/edge/memories", json={
        "content": "operator note needs review", "memory_type": "operator_note", "device_id": "r1",
    })
    assert response.status_code == 201
    memory_id = response.json()["memory_id"]
    assert response.json()["requested_sync_policy"] is None
    assert response.json()["sync_policy"] == "approval_required"
    assert response.json()["sync_state"] == "AWAITING_APPROVAL"
    assert runtime.outbox.pending(10) == []

    first = client.post(f"/api/v1/edge/sync/{memory_id}/approve")
    second = client.post(f"/api/v1/edge/sync/{memory_id}/approve")
    assert first.status_code == second.status_code == 200
    assert first.json()["sync_state"] == "QUEUED"
    assert len(runtime.outbox.pending(10)) == 1
    events = runtime.activity.list(20)
    assert [event.event_type for event in events].count("POLICY_SYNC_APPROVED") == 1
    assert [event.event_type for event in events].count("SYNC_QUEUED") == 1


def test_restricted_approval_is_rechecked_and_rejected(sync_client):
    client, runtime = sync_client
    created = client.post("/api/v1/edge/memories", json={
        "content": "restricted operator note", "memory_type": "operator_note", "sensitivity": "restricted",
    }).json()
    response = client.post(f"/api/v1/edge/sync/{created['memory_id']}/approve")
    assert response.status_code == 409
    assert runtime.outbox.pending(10) == []
    assert runtime.memories.get(created["memory_id"]).sync_policy.value == "local_only"


def test_reject_sets_local_only_without_outbox_and_is_idempotent(sync_client):
    client, runtime = sync_client
    created = client.post("/api/v1/edge/memories", json={
        "content": "please review", "memory_type": "operator_note",
    }).json()
    first = client.post(f"/api/v1/edge/sync/{created['memory_id']}/reject")
    second = client.post(f"/api/v1/edge/sync/{created['memory_id']}/reject")
    assert first.status_code == second.status_code == 200
    assert first.json()["sync_state"] == "LOCAL_ONLY"
    assert first.json()["sync_policy"] == "local_only"
    assert runtime.outbox.pending(10) == []
    types = [event.event_type for event in runtime.activity.list(20)]
    assert types.count("POLICY_LOCAL_ONLY") == 1


def test_automatic_policy_queues_only_after_qdrant_write(sync_client):
    client, runtime = sync_client
    created = client.post("/api/v1/edge/memories", json={
        "content": "new learned maintenance fact", "memory_type": "learned_fact",
    })
    assert created.status_code == 201
    record = created.json()
    assert record["sync_policy"] == "auto" and record["sync_state"] == "QUEUED"
    assert runtime.store.retrieve(record["memory_id"]) is not None
    assert [item.memory_id for item in runtime.outbox.pending(10)] == [record["memory_id"]]
    assert client.get("/api/v1/edge/sync/queue").json()[0]["memory_id"] == record["memory_id"]
    columns = {row["name"] for row in runtime.state_db._connection.execute("PRAGMA table_info(memory_policy)")}
    assert "content" not in columns and "dense" not in columns


def test_approval_rejects_superseded_revision(sync_client):
    client, runtime = sync_client
    first = client.post("/api/v1/edge/memories", json={
        "content": "operator note for review", "memory_type": "operator_note",
    }).json()
    revised = client.patch(f"/api/v1/edge/memories/{first['memory_id']}", json={
        "content": "updated operator note", "parent_revision": 1,
    })
    assert revised.status_code == 200
    stale = client.post(f"/api/v1/edge/sync/{first['memory_id']}/approve")
    assert stale.status_code == 409
    assert runtime.outbox.pending(10) == []


def test_control_plane_failure_never_reports_queued_and_reconcile_recovers(sync_client, monkeypatch):
    client, runtime = sync_client

    def fail_transaction():
        raise sqlite3.OperationalError("injected commit outage")

    monkeypatch.setattr(runtime.state_db, "transaction", fail_transaction)
    response = client.post("/api/v1/edge/memories", json={
        "content": "durable learned maintenance fact", "memory_type": "learned_fact",
    })
    assert response.status_code == 503
    point = runtime.store.list_points()[0]
    memory_id = point.id
    assert point.payload["sync_state"] == "LOCAL_DIRTY"
    assert runtime.outbox.pending(10) == []

    # Reopen only the control plane, as a process restart would; Qdrant is persistent.
    runtime.state_db.close()
    runtime.state_db = EdgeStateDB(runtime.state_db.path)
    runtime.outbox = SyncOutbox(runtime.state_db)
    runtime.activity = ActivityLog(runtime.state_db)
    runtime.memories.state_db = runtime.state_db
    runtime.memories.policy_workflow = PolicyWorkflow(runtime.state_db)
    asyncio.run(runtime.start())
    asyncio.run(runtime.start())
    assert runtime.memories.get(memory_id).sync_state.value == "QUEUED"
    assert [item.memory_id for item in runtime.outbox.pending(10)] == [memory_id]
    assert [e.event_type for e in runtime.activity.list(20)].count("SYNC_QUEUED") == 1


def test_concurrent_approvals_commit_one_outbox_and_one_transition(sync_client):
    client, runtime = sync_client
    created = client.post("/api/v1/edge/memories", json={
        "content": "operator note for review", "memory_type": "operator_note",
    }).json()
    async def approve_twice():
        return await asyncio.gather(
            runtime.memories.approve(created["memory_id"]),
            runtime.memories.approve(created["memory_id"]),
        )

    results = asyncio.run(approve_twice())
    assert all(item.sync_state.value == "QUEUED" for item in results)
    assert len(runtime.outbox.pending(10)) == 1
    types = [event.event_type for event in runtime.activity.list(30)]
    assert types.count("POLICY_SYNC_APPROVED") == 1
    assert types.count("SYNC_QUEUED") == 1
