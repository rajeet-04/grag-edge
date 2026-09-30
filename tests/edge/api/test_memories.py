from fastapi.testclient import TestClient
import pytest

from app.edge.runtime import EdgeRuntime
from app.edge.memory.hybrid_search import MemoryHit
from app.edge.memory.store import MemoryOrigin
from tests.edge.memory.test_memory_service import Store, Embeddings


@pytest.fixture
def client(monkeypatch):
    import app.edge.runtime as runtime_module
    import app.database.neo4j_client as neo4j_module
    import app.schemas.graph_schema as graph_module
    from app.main import app

    stores = []
    def new_runtime():
        store = Store()
        stores.append(store)
        return EdgeRuntime(store, Embeddings())
    monkeypatch.setattr(runtime_module, "EdgeRuntime", new_runtime)
    class Neo4j:
        async def verify_connectivity(self): return False
        async def close(self): pass
    monkeypatch.setattr(neo4j_module, "get_neo4j_client", lambda: Neo4j())
    async def no_graph_init(): return {}
    monkeypatch.setattr(graph_module, "init_graph_schema", no_graph_init)
    with TestClient(app) as test_client:
        yield test_client
    assert stores[0].closed == 1
    assert app.state.edge_runtime is None


def test_memory_create_get_revise_and_filters(client):
    created = client.post("/api/v1/edge/memories", json={"content":"bearing vibration", "device_id":"robot-7", "source_type":"sensor", "source_id":"vib-1", "tags":["bearing"], "importance":"high"})
    assert created.status_code == 201
    item = created.json()
    assert item["revision"] == 1 and item["source_id"] == "vib-1"
    assert client.get(f"/api/v1/edge/memories/{item['memory_id']}").json()["content"] == "bearing vibration"
    revised = client.patch(f"/api/v1/edge/memories/{item['memory_id']}", json={"content":"bearing vibration severe", "parent_revision":1})
    assert revised.status_code == 200 and revised.json()["revision"] == 2
    for params in ({"source":"sensor"}, {"memory_type":"observation"}, {"sync_state":"LOCAL_DIRTY"}, {"importance":"high"}, {"device_id":"robot-7"}, {"tag":"bearing"}, {"from_time":"2000-01-01T00:00:00Z"}, {"to_time":"2100-01-01T00:00:00Z"}):
        assert len(client.get("/api/v1/edge/memories", params=params).json()) == 1
    assert client.get("/api/v1/edge/memories", params={"device_id":"other"}).json() == []


def test_unknown_id_and_empty_search(client):
    assert client.get("/api/v1/edge/memories/unknown").status_code == 404
    assert client.post("/api/v1/edge/search", json={"query":""}).status_code == 422


def test_search_exposes_scores_origin_and_provenance(client):
    record = client.post("/api/v1/edge/memories", json={"content":"pump alarm", "device_id":"r1", "source_type":"sensor", "source_id":"p1"}).json()
    class Search:
        async def search(self, *_):
            return [MemoryHit(record["memory_id"], 0.42, MemoryOrigin.LOCAL, 0.7, 0.3, {})]
    client.app.state.edge_runtime.search = Search()
    response = client.post("/api/v1/edge/search", json={"query":"pump alarm"})
    result = response.json()["results"][0]
    assert result["origin"] == "LOCAL" and result["score"] == 0.42
    assert result["dense_score"] == 0.7 and result["sparse_score"] == 0.3
    assert result["revision"] == 1 and result["source_id"] == "p1"
    revised = client.patch(f"/api/v1/edge/memories/{record['memory_id']}", json={"content":"pump alarm updated", "parent_revision":1}).json()
    assert client.post("/api/v1/edge/search", json={"query":"pump alarm"}).json()["results"] == []
    import anyio
    anyio.run(client.app.state.edge_runtime.memories.tombstone, revised["logical_id"])
    class TombstonedSearch:
        async def search(self, *_):
            return [MemoryHit(revised["memory_id"], 0.4, MemoryOrigin.LOCAL, 0.4, None, {})]
    client.app.state.edge_runtime.search = TombstonedSearch()
    assert client.post("/api/v1/edge/search", json={"query":"pump alarm"}).json()["results"] == []
