import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.edge.memory.models import MemoryRecord, MemoryType, SyncState
from app.edge.memory.store import StoredPoint
from app.edge.runtime import EdgeRuntime
from app.edge.sync.server_client import CloudHealth


class Store:
    def __init__(self): self.points, self.fleet = {}, {}
    def upsert(self, point): self.points[point.id] = point
    def retrieve(self, i): return self.points.get(i)
    def retrieve_fleet(self, i): return self.fleet.get(i)
    def list_points(self): return list(self.points.values())
    def list_fleet_points(self): return list(self.fleet.values())
    def embed_bm25_document(self, _): return {"indices": [1], "values": [1.0]}
    def close(self): pass


class Embeddings:
    async def embed_with_context(self, *_): return [1.0, 0.0, 0.0, 0.0]
    async def embed_text(self, _): return [1.0, 0.0, 0.0, 0.0]
    async def close(self): pass


class Cloud:
    def __init__(self): self.uploaded = []
    def health(self): return CloudHealth.ONLINE
    def ensure_collection(self, _): pass
    def upsert_point(self, point): self.uploaded.append(point.id)
    def delete_points(self, ids): pass
    def close(self): pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.edge.runtime as runtime_module
    import app.database.neo4j_client as neo4j_module
    store, cloud = Store(), Cloud()
    edge = EdgeRuntime(store=store, embedding_service=Embeddings(), state_path=tmp_path / "state.db", remote=cloud)
    monkeypatch.setattr(runtime_module, "EdgeRuntime", lambda: edge)

    class Neo4j:
        async def verify_connectivity(self): return False
        async def close(self): pass

    monkeypatch.setattr(neo4j_module, "get_neo4j_client", lambda: Neo4j())
    from app.main import app
    with TestClient(app) as client:
        yield client, edge, store, cloud


def diverge(client, edge, store):
    """Local rev2 (parent 1) and a fleet rev2 (parent 1) that differ."""
    created = client.post("/api/v1/edge/memories", json={"content": "close valve A first", "memory_type": "procedure"}).json()
    local = client.patch(f"/api/v1/edge/memories/{created['memory_id']}",
        json={"content": "close valve B first", "parent_revision": 1, "sync_policy": "auto"}).json()
    now = datetime.now(timezone.utc)
    fleet = MemoryRecord(memory_id="fleet-rev2", logical_id=local["logical_id"], device_id="robot-2",
        memory_type=MemoryType.PROCEDURE, content="close valve C first", created_at=now, updated_at=now,
        revision=2, parent_revision=1, content_hash=edge.memories.content_hash("close valve C first"),
        sync_state=SyncState.SYNCHRONIZED)
    store.fleet[fleet.memory_id] = StoredPoint(fleet.memory_id, [1.0, 0, 0, 0], {"indices": [1], "values": [1.0]},
        {"record_type": "memory", **fleet.model_dump(mode="json")})
    return local, fleet


def detect(edge):
    asyncio.run(edge.sync._blocking(edge.sync._scan_conflicts))


def test_detection_blocks_upload_and_lists_conflict_with_stats(env):
    client, edge, store, cloud = env
    local, fleet = diverge(client, edge, store)
    detect(edge)
    detect(edge)
    conflicts = client.get("/api/v1/edge/conflicts").json()
    assert len(conflicts) == 1 and conflicts[0]["local_memory_id"] == local["memory_id"]
    detail = client.get(f"/api/v1/edge/conflicts/{conflicts[0]['conflict_id']}").json()
    assert detail["local"]["content"] == "close valve B first" and detail["fleet"]["content"] == "close valve C first"
    assert client.get(f"/api/v1/edge/memories/{local['memory_id']}").json()["sync_state"] == "CONFLICTED"
    assert client.get("/api/v1/edge/stats").json()["open_conflict_count"] == 1
    assert [e for e in edge.activity.list(50) if e.event_type == "CONFLICT_DETECTED"].__len__() == 1
    asyncio.run(edge.sync.run_once())
    assert local["memory_id"] not in cloud.uploaded


@pytest.mark.parametrize("resolution,expected", [("KEEP_LOCAL", "close valve B first"),
                                                 ("ACCEPT_FLEET", "close valve C first"),
                                                 ("MERGE", "close valve B then C")])
def test_resolution_creates_revision_above_both_and_preserves_history(env, resolution, expected):
    client, edge, store, cloud = env
    local, fleet = diverge(client, edge, store)
    detect(edge)
    conflict_id = client.get("/api/v1/edge/conflicts").json()[0]["conflict_id"]
    body = {"resolution": resolution, "merged_content": "close valve B then C" if resolution == "MERGE" else None}
    first = client.post(f"/api/v1/edge/conflicts/{conflict_id}/resolve", json=body)
    assert first.status_code == 200 and first.json()["status"] == "RESOLVED"
    again = client.post(f"/api/v1/edge/conflicts/{conflict_id}/resolve", json=body)
    assert again.status_code == 200 and again.json()["resolution_memory_id"] == first.json()["resolution_memory_id"]
    resolved = client.get(f"/api/v1/edge/memories/{first.json()['resolution_memory_id']}").json()
    assert resolved["content"] == expected and resolved["revision"] == 3 and resolved["parent_revision"] == 2
    assert resolved["source_type"] == "conflict_resolution" and resolved["source_id"] == conflict_id
    ids = {r.memory_id for r in edge.memories.history(local["logical_id"])}
    assert {local["memory_id"], "fleet-rev2", resolved["memory_id"]} <= ids
    assert [e.event_type for e in edge.activity.list(100)].count("CONFLICT_RESOLVED") == 1
    assert client.get("/api/v1/edge/conflicts").json() == []
    assert client.get("/api/v1/edge/stats").json()["open_conflict_count"] == 0
    detect(edge)
    assert client.get("/api/v1/edge/conflicts").json() == []
    asyncio.run(edge.sync.run_once())
    assert resolved["memory_id"] in cloud.uploaded


def test_conflicting_resolution_and_bad_requests_are_rejected(env):
    client, edge, store, cloud = env
    diverge(client, edge, store)
    detect(edge)
    conflict_id = client.get("/api/v1/edge/conflicts").json()[0]["conflict_id"]
    url = f"/api/v1/edge/conflicts/{conflict_id}/resolve"
    assert client.post(url, json={"resolution": "MERGE"}).status_code == 422
    assert client.post(url, json={"resolution": "NEWEST_WINS"}).status_code == 422
    assert client.post("/api/v1/edge/conflicts/nope/resolve", json={"resolution": "KEEP_LOCAL"}).status_code == 404
    assert client.post(url, json={"resolution": "KEEP_LOCAL"}).status_code == 200
    assert client.post(url, json={"resolution": "ACCEPT_FLEET"}).status_code == 409


def test_concurrent_resolution_writes_one_revision_and_one_event(env):
    client, edge, store, cloud = env
    local, fleet = diverge(client, edge, store)
    detect(edge)
    conflict_id = client.get("/api/v1/edge/conflicts").json()[0]["conflict_id"]
    url = f"/api/v1/edge/conflicts/{conflict_id}/resolve"
    with ThreadPoolExecutor(4) as pool:
        codes = list(pool.map(lambda _: client.post(url, json={"resolution": "KEEP_LOCAL"}).status_code, range(4)))
    assert codes == [200] * 4
    assert len([r for r in edge.memories.history(local["logical_id"]) if r.revision == 3]) == 1
    assert [e.event_type for e in edge.activity.list(100)].count("CONFLICT_RESOLVED") == 1


def test_restart_after_claim_reuses_deterministic_revision(env):
    client, edge, store, cloud = env
    local, fleet = diverge(client, edge, store)
    detect(edge)
    conflict = edge.conflicts.list_open()[0]
    real = edge.memories.write_resolution

    async def crash(*_):
        raise RuntimeError("crash before write")

    edge.memories.write_resolution = crash
    with pytest.raises(RuntimeError):
        asyncio.run(edge.conflicts.resolve(conflict.conflict_id, "KEEP_LOCAL", edge.memories))
    assert edge.conflicts.get(conflict.conflict_id).status == "RESOLVING"
    assert client.get("/api/v1/edge/stats").json()["open_conflict_count"] == 1
    edge.memories.write_resolution = real
    done = client.post(f"/api/v1/edge/conflicts/{conflict.conflict_id}/resolve", json={"resolution": "KEEP_LOCAL"}).json()
    assert done["status"] == "RESOLVED" and store.retrieve(done["resolution_memory_id"]) is not None
