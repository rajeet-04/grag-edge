from types import SimpleNamespace

import pytest

from app.edge.memory.store import StoredPoint
from app.edge.sync.server_client import CloudHealth, QdrantServerClient


class FakeQdrant:
    def __init__(self):
        self.collections = {}
        self.points = {}
        self.created = []

    def collection_exists(self, name):
        return name in self.collections

    def create_collection(self, **kwargs):
        self.collections[kwargs["collection_name"]] = kwargs
        self.created.append(kwargs)
        return True

    def upsert(self, collection_name, points, wait=True):
        for point in points:
            self.points[(collection_name, point.id)] = point
        return SimpleNamespace(operation_id=1, status="completed")

    def get_collection(self, name):
        if name not in self.collections:
            raise RuntimeError("not found")
        return SimpleNamespace(status="green")


def point():
    return StoredPoint("123e4567-e89b-12d3-a456-426614174000", [0.1, 0.2], {"indices": [2, 5], "values": [0.3, 0.8]}, {"content": "bearing noise"})


def test_collection_schema_is_idempotent_one_shard_dense_and_idf_sparse():
    remote = FakeQdrant()
    client = QdrantServerClient("http://qdrant", collection="fleet", client=remote)

    client.ensure_collection(2)
    client.ensure_collection(2)

    assert len(remote.created) == 1
    schema = remote.created[0]
    assert schema["shard_number"] == 1
    assert set(schema["vectors_config"]) == {"dense"}
    assert schema["vectors_config"]["dense"].size == 2
    assert schema["vectors_config"]["dense"].distance.value == "Cosine"
    assert set(schema["sparse_vectors_config"]) == {"text"}
    assert schema["sparse_vectors_config"]["text"].modifier.value == "idf"


def test_point_upsert_preserves_vectors_payload_and_replaces_identity():
    remote = FakeQdrant()
    client = QdrantServerClient("http://qdrant", collection="fleet", client=remote)
    first = point()

    client.upsert_point(first)
    client.upsert_point(first)

    assert len(remote.points) == 1
    uploaded = remote.points[("fleet", "123e4567-e89b-12d3-a456-426614174000")]
    assert uploaded.id == first.id
    assert uploaded.vector["dense"] == first.dense
    assert uploaded.vector["text"].indices == [2, 5]
    assert uploaded.vector["text"].values == [0.3, 0.8]
    assert uploaded.payload == first.payload


def test_health_classifies_network_as_offline_and_auth_as_error():
    class FailingClient:
        def __init__(self, error):
            self.error = error

        def get_collections(self):
            raise self.error

    assert QdrantServerClient("x", client=FailingClient(TimeoutError())).health() is CloudHealth.OFFLINE
    assert QdrantServerClient("x", client=FailingClient(Exception("401 unauthorized"))).health() is CloudHealth.ERROR
