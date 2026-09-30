"""One owner for edge storage, retrieval, and memory services."""
from pathlib import Path
from app.edge.memory.hybrid_search import HybridSearchService
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.service import MemoryService
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox
from app.llm.embedding import get_embedding_service


class EdgeRuntime:
    def __init__(self, store=None, embedding_service=None, state_path=None):
        self.embedding_service = embedding_service or get_embedding_service()
        from app.config import get_settings
        settings = get_settings()
        if store is None:
            local = settings.qdrant_edge_path
            store = QdrantEdgeStore(local, local.with_name(local.name + "-fleet"), settings.embedding_dimension)
            store.open()
        self.store = store
        self.state_db = EdgeStateDB(state_path or settings.edge_state_path)
        self.outbox = SyncOutbox(self.state_db)
        self.activity = ActivityLog(self.state_db)
        self.search = HybridSearchService(store, self.embedding_service)
        self.memories = MemoryService(store, self.embedding_service, self.state_db)

    async def start(self):
        """Recover control-plane metadata for Qdrant records written before a crash."""
        await self.memories.reconcile()

    async def close(self):
        try:
            self.store.close()
        finally:
            try:
                self.state_db.close()
            finally:
                close = getattr(self.embedding_service, "close", None)
                if close is not None:
                    await close()
