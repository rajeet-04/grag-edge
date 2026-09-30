"""Dashboard connectivity update < 2 s after a detected network transition (design section 28)."""
import asyncio
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.edge.api.operations import events
from app.edge.sync.server_client import CloudHealth
from tests.edge.api.test_edge_status import Embeddings
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.runtime import EdgeRuntime

TARGET_SECONDS = 2.0


class FlippableCloud:
    def __init__(self): self.state = CloudHealth.ONLINE
    def health(self): return self.state
    def ensure_collection(self, dimension): pass
    def upsert_point(self, point): pass
    def close(self): pass


async def _next_event_chunk(iterator, event_type, deadline):
    while time.monotonic() < deadline:
        chunk = await asyncio.wait_for(iterator.__anext__(), timeout=max(0.01, deadline - time.monotonic()))
        if f"event: {event_type}" in chunk:
            return chunk
    raise AssertionError(f"{event_type} not delivered before deadline")


def test_link_transitions_reach_the_event_stream_and_status_within_two_seconds(tmp_path):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
    store.open()
    cloud = FlippableCloud()
    edge = EdgeRuntime(store=store, embedding_service=Embeddings(), state_path=tmp_path / "state.db", remote=cloud)
    edge.snapshots = None
    edge.sync.snapshots = None

    class Request:
        headers = {}
        app = SimpleNamespace(state=SimpleNamespace(edge_runtime=edge))
        async def is_disconnected(self): return False

    async def scenario():
        edge.connectivity.run_once()
        stream = (await events(Request())).body_iterator
        for _ in range(3):  # drain startup events until the stream is idle
            if (await stream.__anext__()) == ": heartbeat\n\n":
                break
        latencies = {}
        for target, kind in ((CloudHealth.OFFLINE, "CLOUD_LINK_DOWN"), (CloudHealth.ONLINE, "CLOUD_LINK_UP")):
            cloud.state = target
            started = time.monotonic()
            await asyncio.to_thread(edge.connectivity.run_once)  # the detected transition
            assert edge.connectivity.current()["connectivity"] == target.value
            await _next_event_chunk(stream, kind, started + TARGET_SECONDS)
            latencies[kind] = time.monotonic() - started
        await stream.aclose()
        return latencies

    latencies = asyncio.run(scenario())
    assert all(value < TARGET_SECONDS for value in latencies.values()), latencies
    store.close(); edge.state_db.close()
