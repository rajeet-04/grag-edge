import time

from fastapi.testclient import TestClient

from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.runtime import EdgeRuntime
from app.edge.state.activity import ActivityEvent
from app.edge.sync.server_client import CloudHealth


class Embeddings:
    async def embed_with_context(self, text, task_type): return [0.1, 0.2, 0.3, 0.4]
    async def embed_text(self, text): return [0.1, 0.2, 0.3, 0.4]
    async def close(self): pass


class OfflineCloud:
    def health(self): return CloudHealth.OFFLINE
    def ensure_collection(self, dimension): raise AssertionError("offline cloud must not be required at startup")
    def upsert_point(self, point): raise AssertionError("offline cloud must not receive payload")
    def close(self): pass


def client_for(tmp_path, monkeypatch):
    import app.edge.runtime as runtime_module
    import app.database.neo4j_client as neo4j_module
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
    store.open()
    edge = EdgeRuntime(store=store, embedding_service=Embeddings(), state_path=tmp_path / "state.db", remote=OfflineCloud())
    monkeypatch.setattr(runtime_module, "EdgeRuntime", lambda: edge)
    class Neo4j:
        async def verify_connectivity(self): return False
        async def close(self): pass
    monkeypatch.setattr(neo4j_module, "get_neo4j_client", lambda: Neo4j())
    from app.main import app
    return TestClient(app), edge


def test_api_is_ready_and_local_memory_search_works_while_cloud_is_offline(tmp_path, monkeypatch):
    client, edge = client_for(tmp_path, monkeypatch)
    with client:
        status = client.get("/api/v1/edge/status")
        assert status.status_code == 200
        assert status.json()["status"] == "READY"
        assert status.json()["connectivity"] == "OFFLINE"
        created = client.post("/api/v1/edge/memories", json={"content": "offline bearing inspection note", "sync_policy": "local_only"})
        assert created.status_code == 201
        found = client.post("/api/v1/edge/search", json={"query": "bearing inspection", "mode": "hybrid"})
        assert found.status_code == 200 and found.json()["results"]
        assert client.get("/api/v1/edge/sync/status").json()["connectivity"]["connectivity"] == "OFFLINE"
        assert client.get("/api/v1/edge/stats").json()["local_memory_count"] == 1
    assert len(edge._background) == 2
    assert all(task.done() for task in edge._background)


def test_manual_sync_returns_without_waiting_for_remote_call(tmp_path, monkeypatch):
    client, edge = client_for(tmp_path, monkeypatch)
    with client:
        started = time.monotonic()
        response = client.post("/api/v1/edge/sync/run")
        elapsed = time.monotonic() - started
        assert response.status_code == 202
        assert response.json()["status"] in ("SCHEDULED", "RUNNING")
        assert elapsed < 0.2


def test_sse_reconnect_uses_persisted_last_event_id_once(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.edge.api.operations import events

    client, edge = client_for(tmp_path, monkeypatch)
    with client:
        cursor = edge.activity.latest_id()
        event = ActivityEvent(event_type="TEST_AFTER_CURSOR", device_id=edge.device_id,
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc), message="after cursor")
        edge.activity.append(event)

        class Request:
            headers = {"last-event-id": cursor}
            app = SimpleNamespace(state=SimpleNamespace(edge_runtime=edge))
            async def is_disconnected(self): return False

        response = asyncio.run(events(Request()))
        assert response.media_type == "text/event-stream"
        chunk = asyncio.run(response.body_iterator.__anext__())
        assert f"id: {event.event_id}" in chunk
        assert "event: TEST_AFTER_CURSOR" in chunk
        assert edge.activity.after(event.event_id) == []
        heartbeat = asyncio.run(response.body_iterator.__anext__())
        assert heartbeat == ": heartbeat\n\n"
        asyncio.run(response.body_iterator.aclose())


def test_revision_sqlite_failure_returns_503_instead_of_success(tmp_path, monkeypatch):
    import sqlite3
    client, edge = client_for(tmp_path, monkeypatch)
    with client:
        created = client.post("/api/v1/edge/memories", json={"content": "revision that fails metadata commit"})
        assert created.status_code == 201
        def fail_transaction():
            raise sqlite3.OperationalError("injected control-plane failure")
        monkeypatch.setattr(edge.state_db, "transaction", fail_transaction)
        response = client.patch(f"/api/v1/edge/memories/{created.json()['memory_id']}", json={
            "content": "revised value", "parent_revision": 1,
        })
        assert response.status_code == 503
