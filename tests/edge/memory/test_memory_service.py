from __future__ import annotations

from uuid import uuid4

import pytest

from app.edge.memory.models import CreateMemory, ReviseMemory
from app.edge.memory.service import MemoryService
from app.edge.memory.store import StoredPoint
from app.edge.memory.qdrant_store import QdrantEdgeStore


class Store:
    def __init__(self):
        self.points = {}
        self.closed = 0

    def upsert(self, point):
        self.points[point.id] = point

    def retrieve(self, point_id):
        return self.points.get(point_id)

    def list_points(self):
        return list(self.points.values())

    def close(self):
        self.closed += 1

    def embed_bm25_document(self, text):
        return {"indices": [1], "values": [float(len(text))]}


class Embeddings:
    async def embed_with_context(self, text, task_type):
        assert task_type == "search_document"
        return [float(len(text)), 0.0, 0.0, 1.0]


@pytest.mark.asyncio
async def test_revision_provenance_hash_history_and_tombstone():
    store = Store()
    service = MemoryService(store, Embeddings())
    first = await service.create(CreateMemory(content="Inspect valve", device_id="robot-1", source_type="robot", source_id="cam-2"))
    assert first.revision == 1 and first.parent_revision is None
    assert first.content_hash == service.content_hash("Inspect valve")
    assert store.retrieve(first.memory_id).dense == [13.0, 0.0, 0.0, 1.0]
    assert store.retrieve(first.memory_id).sparse is not None

    second = await service.revise(first.logical_id, ReviseMemory(content="Inspect valve leak", parent_revision=1))
    assert second.revision == 2 and second.parent_revision == 1
    assert service.get(first.memory_id).content == "Inspect valve"
    assert [r.revision for r in service.history(first.logical_id)] == [1, 2]
    assert second.content_hash == service.content_hash("Inspect valve leak")
    deleted = await service.tombstone(first.logical_id)
    assert deleted.is_deleted and deleted.revision == 3
    assert service.current(first.logical_id) is None


@pytest.mark.asyncio
async def test_duplicate_revision_id_and_stale_parent_are_rejected():
    store = Store()
    service = MemoryService(store, Embeddings())
    first = await service.create(CreateMemory(content="one", memory_id=str(uuid4())))
    with pytest.raises(ValueError, match="already exists"):
        await service.create(CreateMemory(content="two", memory_id=first.memory_id))
    with pytest.raises(ValueError, match="stale"):
        await service.revise(first.logical_id, ReviseMemory(content="two", parent_revision=0))


@pytest.mark.asyncio
async def test_revision_history_survives_store_reopen(tmp_path):
    local, fleet = tmp_path / "local", tmp_path / "fleet"
    store = QdrantEdgeStore(local, fleet, 4)
    store.open()
    service = MemoryService(store, Embeddings())
    first = await service.create(CreateMemory(content="persist this"))
    second = await service.revise(first.logical_id, ReviseMemory(content="persist revision two", parent_revision=1))
    await service.tombstone(first.logical_id)
    store.close()
    reopened = QdrantEdgeStore(local, fleet, 4)
    reopened.open()
    restored = MemoryService(reopened, Embeddings())
    history = restored.history(first.logical_id)
    assert [r.memory_id for r in history[:2]] == [first.memory_id, second.memory_id]
    assert history[-1].revision == 3 and history[-1].is_deleted
    assert restored.get(first.memory_id).content == "persist this"
    assert restored.current(first.logical_id) is None
    assert restored.list() == []
    reopened.close()
