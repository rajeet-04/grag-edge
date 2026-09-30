"""One owner for edge storage, retrieval, and memory services."""
from pathlib import Path
from app.edge.memory.hybrid_search import HybridSearchService
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.service import MemoryService
from app.llm.embedding import get_embedding_service


class EdgeRuntime:
    def __init__(self, store=None, embedding_service=None):
        self.embedding_service = embedding_service or get_embedding_service()
        if store is None:
            from app.config import get_settings
            settings = get_settings()
            local = settings.qdrant_edge_path
            store = QdrantEdgeStore(local, local.with_name(local.name + "-fleet"), settings.embedding_dimension)
            store.open()
        self.store = store
        self.search = HybridSearchService(store, self.embedding_service)
        self.memories = MemoryService(store, self.embedding_service)

    async def close(self):
        self.store.close()
        close = getattr(self.embedding_service, "close", None)
        if close is not None:
            await close()
