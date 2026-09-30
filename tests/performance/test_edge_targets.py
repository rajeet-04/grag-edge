"""Observability contract and latency targets on a deterministic dataset."""
import statistics
import time

from fastapi.testclient import TestClient

from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.runtime import EdgeRuntime
from app.edge.sync.server_client import CloudHealth
from tests.e2e._edge_harness import Embeddings

BASE = "/api/v1/edge"


class Cloud:
    def health(self): return CloudHealth.OFFLINE
    def ensure_collection(self, d): pass
    def upsert_point(self, p): pass
    def close(self): pass


def make_client(tmp_path, monkeypatch):
    import app.edge.runtime as runtime_module
    import app.database.neo4j_client as neo4j_module
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
    store.open()
    edge = EdgeRuntime(store=store, embedding_service=Embeddings(), state_path=tmp_path / "state.db", remote=Cloud())
    monkeypatch.setattr(runtime_module, "EdgeRuntime", lambda: edge)

    class Neo4j:
        async def verify_connectivity(self): return False
        async def close(self): pass
    monkeypatch.setattr(neo4j_module, "get_neo4j_client", lambda: Neo4j())
    from app.main import app
    return TestClient(app), edge


def p95(values):
    return statistics.quantiles(values, n=20)[-1]


def test_stats_expose_full_observability_contract(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    with client:
        client.post(f"{BASE}/memories", json={"content": "bearing note", "sync_policy": "auto",
            "memory_type": "learned_fact", "importance": "high", "confidence": 0.95})
        assert client.post(f"{BASE}/search", json={"query": "bearing", "mode": "hybrid"}).status_code == 200
        stats = client.get(f"{BASE}/stats").json()
    for key in ("local_memory_count", "fleet_memory_count", "pending_sync", "open_conflict_count", "last_sync",
                "last_fleet_refresh", "search_latency_ms", "origin_counts", "sync_success_count", "sync_failure_count", "connectivity"):
        assert key in stats, key
    assert stats["origin_counts"] == {"LOCAL": 1, "FLEET": 0}
    assert stats["last_fleet_refresh"] is None
    assert isinstance(stats["search_latency_ms"], float) and stats["search_latency_ms"] >= 0


def test_stats_report_last_fleet_refresh_from_checkpoint(tmp_path, monkeypatch):
    client, edge = make_client(tmp_path, monkeypatch)
    with client:
        with edge.state_db.transaction() as conn:
            conn.execute("INSERT INTO sync_checkpoints(checkpoint_id,value,updated_at) VALUES('fleet','{}','2026-09-30T10:00:00+00:00')")
        assert client.get(f"{BASE}/stats").json()["last_fleet_refresh"] == "2026-09-30T10:00:00+00:00"


def test_events_stream_is_backed_by_persisted_activity(tmp_path, monkeypatch):
    client, edge = make_client(tmp_path, monkeypatch)
    with client:
        client.post(f"{BASE}/memories", json={"content": "note", "sync_policy": "local_only"})
        events = client.get(f"{BASE}/activity").json()
        assert events and all("event_id" in e for e in events)


def test_local_search_write_and_status_meet_targets(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    with client:
        writes = []
        for i in range(60):
            start = time.perf_counter()
            r = client.post(f"{BASE}/memories", json={"content": f"maintenance record {i} for pump station {i % 7}", "sync_policy": "local_only"})
            writes.append((time.perf_counter() - start) * 1000)
            assert r.status_code == 201
        searches, statuses = [], []
        for i in range(40):
            start = time.perf_counter()
            assert client.post(f"{BASE}/search", json={"query": f"pump station {i % 7}", "mode": "hybrid"}).status_code == 200
            searches.append((time.perf_counter() - start) * 1000)
            start = time.perf_counter()
            assert client.get(f"{BASE}/status").status_code == 200
            statuses.append((time.perf_counter() - start) * 1000)
        reported = client.get(f"{BASE}/stats").json()
    assert p95(searches) < 250, p95(searches)
    assert p95(writes) < 300, p95(writes)
    assert max(statuses) < 100, max(statuses)
    assert reported["search_latency_ms"] is not None
