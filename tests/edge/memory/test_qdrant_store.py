from pathlib import Path
from uuid import uuid4

import pytest

from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.store import StoredPoint


def test_point_persists_across_store_reopen(tmp_path: Path):
    local_path = tmp_path / "mutable-local"
    fleet_path = tmp_path / "immutable-fleet"
    point = StoredPoint(
        id=str(uuid4()),
        dense=[0.0, 0.0, 0.0, 1.0],
        sparse={"indices": [12, 29], "values": [1.0, 2.0]},
        payload={"content": "valve pressure alert", "revision": 3},
    )

    store = QdrantEdgeStore(local_path, fleet_path, embedding_dimension=4)
    store.open()
    store.upsert_local(point)
    store.close()

    reopened = QdrantEdgeStore(local_path, fleet_path, embedding_dimension=4)
    reopened.open()
    result = reopened.retrieve_local(point.id)
    assert result is not None
    assert result.id == point.id
    assert result.dense == point.dense
    assert result.sparse == point.sparse
    assert result.payload == point.payload
    assert reopened.retrieve_fleet(point.id) is None
    reopened.close()


def test_confirmed_cleanup_can_delete_exact_local_point(tmp_path: Path):
    point = StoredPoint(str(uuid4()), [0.0, 0.0, 0.0, 1.0], None, {"revision": 1})
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", embedding_dimension=4)
    store.open()
    store.upsert_local(point)

    store.delete_local(point.id)

    assert store.retrieve_local(point.id) is None
    store.close()


def test_dense_dimension_mismatch_is_rejected_without_mutating_shard(tmp_path: Path):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", embedding_dimension=4)
    store.open()
    point = StoredPoint(str(uuid4()), [0.1, 0.2], None, {"content": "too short"})
    with pytest.raises(ValueError, match="dimension 4"):
        store.upsert_local(point)
    assert store.retrieve_local(point.id) is None
    store.close()


def test_existing_empty_shard_directory_has_actionable_error(tmp_path: Path):
    local_path = tmp_path / "local"
    local_path.mkdir()
    with pytest.raises(RuntimeError, match="empty or corrupt"):
        QdrantEdgeStore(local_path, tmp_path / "fleet", embedding_dimension=4).open()
