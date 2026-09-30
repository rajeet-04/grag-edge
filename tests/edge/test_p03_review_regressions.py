"""Native persistence/API regressions found during the P03 review."""
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.edge.memory.models import CreateMemory, ReviseMemory
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.service import MemoryService
from app.edge.runtime import EdgeRuntime


class DelayedEmbeddings:
    async def embed_with_context(self, text, task_type):
        await asyncio.sleep(0.01)
        if "obsolete" in text:
            return [1.0, 0.0]
        if "fleet" in text:
            return [0.0, 1.0]
        return [0.8, 0.6]

    async def embed_text(self, text):
        return [1.0, 0.0]

    async def close(self):
        pass


def make_store(root: Path):
    store = QdrantEdgeStore(root / "local", root / "fleet", 2)
    store.open()
    return store


@pytest.fixture
def native_api(tmp_path, monkeypatch):
    async def seed():
        fleet_store = QdrantEdgeStore(tmp_path / "fleet", tmp_path / "unused-fleet", 2)
        fleet_store.open()
        fleet = await MemoryService(fleet_store, DelayedEmbeddings()).create(
            CreateMemory(content="fleet inspection procedure", source_type="fleet")
        )
        fleet_store.close()

        store = make_store(tmp_path)
        service = MemoryService(store, DelayedEmbeddings())
        obsolete = await service.create(CreateMemory(content="obsolete pump pump pump pump alarm"))
        live = await service.create(CreateMemory(content="live pump alarm"))
        await service.tombstone(obsolete.logical_id)
        store.close()
        return fleet, obsolete, live

    fleet, obsolete, live = asyncio.run(seed())
    runtime = EdgeRuntime(make_store(tmp_path), DelayedEmbeddings(), state_path=tmp_path / "state.db")

    import app.edge.runtime as runtime_module
    import app.database.neo4j_client as neo4j_module

    monkeypatch.setattr(runtime_module, "EdgeRuntime", lambda: runtime)

    class Neo4j:
        async def verify_connectivity(self):
            return False

        async def close(self):
            pass

    monkeypatch.setattr(neo4j_module, "get_neo4j_client", lambda: Neo4j())
    from app.main import app

    with TestClient(app) as client:
        yield client, fleet, obsolete, live


def test_concurrent_duplicate_create_and_stale_revision_are_serialized(tmp_path):
    async def scenario():
        store = make_store(tmp_path)
        service = MemoryService(store, DelayedEmbeddings())
        memory_id = "00000000-0000-0000-0000-000000000001"
        created = await asyncio.gather(
            service.create(CreateMemory(memory_id=memory_id, content="first")),
            service.create(CreateMemory(memory_id=memory_id, content="duplicate")),
            return_exceptions=True,
        )
        assert sum(not isinstance(item, Exception) for item in created) == 1
        assert sum(isinstance(item, ValueError) for item in created) == 1
        first = next(item for item in created if not isinstance(item, Exception))
        revised = await asyncio.gather(
            service.revise(first.logical_id, ReviseMemory(content="branch A", parent_revision=1)),
            service.revise(first.logical_id, ReviseMemory(content="branch B", parent_revision=1)),
            return_exceptions=True,
        )
        assert sum(not isinstance(item, Exception) for item in revised) == 1
        assert sum(isinstance(item, ValueError) for item in revised) == 1
        history = service.history(first.logical_id)
        assert [item.revision for item in history] == [1, 2]
        store.close()

    asyncio.run(scenario())


def test_concurrent_revise_and_tombstone_leave_one_linear_history(tmp_path):
    async def scenario():
        store = make_store(tmp_path)
        service = MemoryService(store, DelayedEmbeddings())
        first = await service.create(CreateMemory(content="initial"))
        results = await asyncio.gather(
            service.revise(first.logical_id, ReviseMemory(content="updated", parent_revision=1)),
            service.tombstone(first.logical_id),
            return_exceptions=True,
        )
        history = service.history(first.logical_id)
        revisions = [record.revision for record in history]
        assert revisions == list(range(1, len(revisions) + 1))
        assert history[-1].is_deleted
        assert sum(not isinstance(item, Exception) for item in results) >= 1
        store.close()

    asyncio.run(scenario())


def test_logical_identity_cannot_be_reused_after_tombstone(tmp_path):
    async def scenario():
        store = make_store(tmp_path)
        service = MemoryService(store, DelayedEmbeddings())
        first = await service.create(CreateMemory(content="one"))
        await service.tombstone(first.logical_id)
        with pytest.raises(ValueError, match="logical_id"):
            await service.create(CreateMemory(logical_id=first.logical_id, content="second root"))
        assert [item.revision for item in service.history(first.logical_id)] == [1, 2]
        store.close()

    asyncio.run(scenario())


def test_memory_ids_are_canonical_and_cannot_collide_with_fleet(native_api):
    client, fleet, _, _ = native_api
    response = client.post(
        "/api/v1/edge/memories",
        json={"memory_id": fleet.memory_id.upper(), "content": "duplicate fleet point"},
    )
    assert response.status_code == 409
    created = client.post(
        "/api/v1/edge/memories",
        json={"memory_id": "00000000-0000-0000-0000-000000000ABC", "content": "canonical ID"},
    )
    assert created.status_code == 201
    assert created.json()["memory_id"] == "00000000-0000-0000-0000-000000000abc"


def test_fleet_record_can_be_inspected_and_listed(native_api):
    client, fleet, _, _ = native_api
    assert client.get(f"/api/v1/edge/memories/{fleet.memory_id}").status_code == 200
    listed = client.get("/api/v1/edge/memories", params={"source": "fleet"}).json()
    assert any(item["memory_id"] == fleet.memory_id for item in listed)
    response = client.patch(
        f"/api/v1/edge/memories/{fleet.memory_id}",
        json={"content": "mutate fleet", "parent_revision": 1},
    )
    assert response.status_code == 409


def test_fleet_search_preserves_fleet_origin(native_api):
    client, fleet, _, _ = native_api
    results = client.post(
        "/api/v1/edge/search", json={"query": "fleet inspection", "mode": "keyword"}
    ).json()["results"]
    assert any(item["memory_id"] == fleet.memory_id and item["origin"] == "FLEET" for item in results)


@pytest.mark.parametrize("mode", ["semantic", "keyword", "hybrid"])
def test_obsolete_nearest_hit_does_not_starve_live_top_one(native_api, mode):
    client, _, _, live = native_api
    results = client.post(
        "/api/v1/edge/search", json={"query": "pump alarm", "mode": mode, "limit": 1}
    ).json()["results"]
    assert [item["memory_id"] for item in results] == [live.memory_id]


def test_malformed_memory_id_is_a_client_error(native_api):
    client, *_ = native_api
    response = client.get("/api/v1/edge/memories/not-a-uuid")
    assert response.status_code in (404, 422), f"invalid ID returned HTTP {response.status_code}"


def test_whitespace_search_is_a_client_error(native_api):
    client, *_ = native_api
    response = client.post("/api/v1/edge/search", json={"query": "   "})
    assert response.status_code == 422, f"blank search returned HTTP {response.status_code}"


def test_naive_list_timestamp_is_a_client_error(native_api):
    client, *_ = native_api
    response = client.get(
        "/api/v1/edge/memories", params={"from_time": "2000-01-01T00:00:00"}
    )
    assert response.status_code == 422, f"naive timestamp returned HTTP {response.status_code}"


def test_tombstoned_memory_cannot_be_revised(native_api):
    client, _, obsolete, _ = native_api
    response = client.patch(
        f"/api/v1/edge/memories/{obsolete.memory_id}",
        json={"content": "resurrected", "parent_revision": 1},
    )
    assert response.status_code in (404, 409), f"tombstone PATCH returned HTTP {response.status_code}"
