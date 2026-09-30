"""Robot B keeps its own fleet checkpoint across a restart (opt-in: real Qdrant Server via docker exec).

QDRANT_LIVE_DOCKER_CONTAINER=grag-api uv run pytest tests/e2e/test_robot_b_restart.py
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from app.edge.memory.models import MemoryRecord, MemoryType
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.store import MemoryOrigin
from app.edge.runtime import EdgeRuntime
from tests.e2e._edge_harness import CapturingCloud, Embeddings
from tests.edge.sync.test_snapshot_live import DockerCloud, DockerTransport

pytestmark = pytest.mark.skipif(not os.getenv("QDRANT_LIVE_DOCKER_CONTAINER"), reason="requires opt-in cloud network helper")


class Embeddings768(Embeddings):
    async def embed_with_context(self, text, task_type): return [1.0] + [0.0] * 767
    async def embed_text(self, text): return [1.0] + [0.0] * 767


class RecordingTransport(DockerTransport):
    def __init__(self, cloud):
        super().__init__(cloud)
        self.calls = []

    async def handle_async_request(self, request):
        self.calls.append((request.method, request.url.path))
        return await super().handle_async_request(request)


def open_robot_b(tmp_path, cloud):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 768)
    store.open()
    edge = EdgeRuntime(store=store, embedding_service=Embeddings768(), state_path=tmp_path / "state.db", remote=CapturingCloud())
    transport = RecordingTransport(cloud)
    edge.snapshots.client = httpx.AsyncClient(transport=transport)
    return edge, transport


def checkpoint(edge):
    with edge.state_db._lock:
        row = edge.state_db._connection.execute("SELECT value FROM sync_checkpoints WHERE checkpoint_id='fleet'").fetchone()
    return json.loads(row["value"]) if row else None


async def test_robot_b_restart_keeps_fleet_checkpoint_without_redownload(tmp_path):
    cloud = DockerCloud(os.environ["QDRANT_LIVE_DOCKER_CONTAINER"])
    collection = "p11_restart_" + uuid4().hex
    base = "/collections/" + collection
    cloud.request("PUT", base, {"shard_number": 1, "vectors": {"dense": {"size": 768, "distance": "Cosine"}},
                                "sparse_vectors": {"text": {"modifier": "idf"}}})
    now = datetime.now(timezone.utc)
    content = "Robot A replaced pump seal"
    record = MemoryRecord(memory_id=str(uuid4()), logical_id=str(uuid4()), device_id="ROBOT-01", content=content, revision=1,
                          created_at=now, updated_at=now, content_hash=hashlib.sha256(content.encode()).hexdigest(),
                          memory_type=MemoryType.LEARNED_FACT)
    cloud.request("PUT", base + "/points?wait=true", {"points": [{
        "id": record.memory_id, "vector": {"dense": [1.0] + [0.0] * 767, "text": {"indices": [1], "values": [1.0]}},
        "payload": {**record.model_dump(mode="json"), "record_type": "memory"}}]})

    edge, transport = open_robot_b(tmp_path, cloud)
    edge.snapshots.base_url = "http://cloud" + base + "/shards/0/snapshot"
    await edge.start()
    await edge.snapshots.bootstrap_if_missing()
    before = checkpoint(edge)
    assert before and before["generation"]
    assert any(hit.origin is MemoryOrigin.FLEET and hit.payload["device_id"] == "ROBOT-01"
               for hit in edge.store.query_dense([1.0] + [0.0] * 767, 10, MemoryOrigin.FLEET))
    await edge.close()

    edge, transport = open_robot_b(tmp_path, cloud)
    edge.snapshots.base_url = "http://cloud" + base + "/shards/0/snapshot"
    await edge.start()
    assert checkpoint(edge)["generation"] == before["generation"]
    assert checkpoint(edge)["refresh_id"] == before["refresh_id"]
    result = await edge.snapshots.bootstrap_if_missing()
    assert result.status == "UNCHANGED" and transport.calls == []  # no full re-download after restart
    assert edge.store.retrieve_fleet(record.memory_id).payload["device_id"] == "ROBOT-01"
    await edge.close()
