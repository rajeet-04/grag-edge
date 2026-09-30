from uuid import UUID, uuid4

import pytest

from app.edge.memory.hybrid_search import (
    HybridSearchService,
    MemoryOrigin,
    SearchMode,
)
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.store import StoredPoint


class DeterministicEmbedding:
    async def embed_text(self, text: str) -> list[float]:
        if "pump" in text.lower() or "overheat" in text.lower():
            return [1.0, 0.0]
        return [0.0, 1.0]


async def make_service(tmp_path, *, empty_fleet=False):
    local_path = tmp_path / "local"
    fleet_path = tmp_path / "fleet"
    if empty_fleet:
        fleet_path.mkdir()
    store = QdrantEdgeStore(local_path, fleet_path, embedding_dimension=2)
    store.open()
    service = HybridSearchService(store, embedding_service=DeterministicEmbedding())
    return store, service


def add_point(store, text, dense, *, point_id=None, origin=MemoryOrigin.LOCAL):
    from app.edge.memory.bm25 import EdgeBm25Indexer

    indexer = EdgeBm25Indexer(store)
    point = StoredPoint(
        id=point_id or str(uuid4()),
        dense=dense,
        sparse=indexer.embed_document(text),
        payload={"content": text},
    )
    if origin is not MemoryOrigin.LOCAL:
        raise AssertionError("this P02 fixture only writes through the local memory API")
    store.upsert_local(point)
    return point


@pytest.mark.asyncio
async def test_semantic_search_retrieves_paraphrased_memory(tmp_path):
    store, service = await make_service(tmp_path)
    target = add_point(
        store, "Pump P-41 temperature is above normal", [1.0, 0.0]
    )
    add_point(store, "Conveyor C-19 belt tension is stable", [0.0, 1.0])

    results = await service.search("which pump is overheating?", SearchMode.SEMANTIC)
    assert results[0].point_id == target.id
    assert results[0].origin is MemoryOrigin.LOCAL
    assert results[0].dense_score is not None
    assert results[0].sparse_score is None
    store.close()


@pytest.mark.asyncio
async def test_hybrid_deduplicates_and_retains_both_channel_scores(tmp_path):
    store, service = await make_service(tmp_path)
    target_id = str(uuid4())
    add_point(store, "Pump P-41 pressure is rising", [1.0, 0.0], point_id=target_id)
    add_point(store, "Conveyor C-19 alignment is stable", [0.0, 1.0])

    results = await service.search("Pump P-41 pressure", SearchMode.HYBRID)
    hits = [hit for hit in results if hit.point_id == target_id]
    assert len(hits) == 1
    assert hits[0].dense_score is not None
    assert hits[0].sparse_score is not None
    assert hits[0].score == pytest.approx(1 / 61 + 1 / 61)
    store.close()


@pytest.mark.asyncio
async def test_keyword_mode_returns_exact_identifier_result(tmp_path):
    store, service = await make_service(tmp_path)
    target = add_point(store, "Pump P-41 pressure sensor fault", [0.0, 1.0])
    add_point(store, "Conveyor C-19 belt tension", [1.0, 0.0])

    results = await service.search("P-41", SearchMode.KEYWORD)
    assert results[0].point_id == target.id
    assert results[0].sparse_score is not None
    assert results[0].dense_score is None
    store.close()


@pytest.mark.asyncio
async def test_equal_rank_results_are_sorted_by_point_id(tmp_path):
    store, service = await make_service(tmp_path)
    ids = sorted([str(uuid4()), str(uuid4())], key=lambda value: UUID(value).hex)
    for point_id in reversed(ids):
        add_point(store, "Pump P-41 inspection report", [1.0, 0.0], point_id=point_id)

    first = await service.search("Pump P-41", SearchMode.HYBRID)
    second = await service.search("Pump P-41", SearchMode.HYBRID)
    assert [hit.point_id for hit in first] == ids
    assert [hit.point_id for hit in second] == ids
    store.close()


@pytest.mark.asyncio
async def test_empty_query_is_rejected_and_empty_fleet_keeps_local_search(tmp_path):
    store, service = await make_service(tmp_path, empty_fleet=True)
    target = add_point(store, "Pump P-41 overheat procedure", [1.0, 0.0])

    with pytest.raises(ValueError, match="query must not be empty"):
        await service.search("   ", SearchMode.SEMANTIC)
    results = await service.search("pump overheat", SearchMode.SEMANTIC)
    assert results[0].point_id == target.id
    assert all(hit.origin is MemoryOrigin.LOCAL for hit in results)
    store.close()


@pytest.mark.asyncio
async def test_fleet_results_keep_fleet_origin(tmp_path):
    fleet_path = tmp_path / "fleet"
    seeder = QdrantEdgeStore(fleet_path, tmp_path / "seed-fleet", embedding_dimension=2)
    seeder.open()
    target = add_point(seeder, "Fleet procedure for Pump P-41", [1.0, 0.0])
    seeder.close()

    store = QdrantEdgeStore(tmp_path / "local", fleet_path, embedding_dimension=2)
    store.open()
    service = HybridSearchService(store, embedding_service=DeterministicEmbedding())
    results = await service.search("pump overheating", SearchMode.SEMANTIC)
    assert results[0].point_id == target.id
    assert results[0].origin is MemoryOrigin.FLEET
    store.close()
