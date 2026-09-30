"""Shared helpers: real native Edge store + SQLite state, capturing fake cloud."""
import asyncio
from pathlib import Path

from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.runtime import EdgeRuntime
from app.edge.sync.server_client import CloudHealth


class Embeddings:
    async def embed_with_context(self, text, task_type): return [0.1, 0.2, 0.3, 0.4]
    async def embed_text(self, text): return [0.1, 0.2, 0.3, 0.4]
    async def close(self): pass


class CapturingCloud:
    """Records every remote call so tests can assert exactly what crossed the boundary."""

    def __init__(self, health=CloudHealth.ONLINE):
        self._health = health
        self.calls: list[tuple[str, object]] = []
        self.uploaded: list = []

    def health(self):
        return self._health

    def ensure_collection(self, dimension): self.calls.append(("ensure_collection", dimension))

    def upsert_point(self, point):
        self.calls.append(("upsert_point", point.id))
        self.uploaded.append(point)

    def delete_points(self, ids, *a, **k): self.calls.append(("delete_points", tuple(ids)))
    def close(self): pass


def open_runtime(tmp_path: Path, cloud) -> EdgeRuntime:
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
    store.open()
    edge = EdgeRuntime(store=store, embedding_service=Embeddings(), state_path=tmp_path / "state.db", remote=cloud)
    # No live Qdrant Server in unit-level e2e: sync confirmation stops at UPLOADED.
    edge.snapshots = None
    edge.sync.snapshots = None
    return edge


def run(coro):
    return asyncio.run(coro)
