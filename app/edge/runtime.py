"""One owner for local services and cloud synchronization lifecycle."""
import asyncio
from pathlib import Path

from app.edge.conflicts import ConflictService
from app.edge.memory.hybrid_search import HybridSearchService
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.service import MemoryService
from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.connectivity import ConnectivityMonitor
from app.edge.sync.outbox import SyncOutbox
from app.edge.sync.server_client import QdrantServerClient
from app.edge.sync.service import SyncService
from app.edge.sync.snapshot import FleetSnapshotService
from app.llm.embedding import get_embedding_service


class EdgeRuntime:
    def __init__(self, store=None, embedding_service=None, state_path=None, remote=None):
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
        self.search = HybridSearchService(store, self.embedding_service, self.state_db)
        self.memories = MemoryService(store, self.embedding_service, self.state_db)
        self.device_id = settings.device_id
        self.connectivity_interval_seconds = settings.connectivity_interval_seconds
        self.sync_interval_seconds = settings.sync_interval_seconds
        self.cloud = remote or QdrantServerClient(settings.qdrant_url, settings.qdrant_collection, settings.qdrant_api_key)
        self.connectivity = ConnectivityMonitor(self.cloud, self.state_db, self.activity, self.device_id)
        self.snapshots = FleetSnapshotService(store,self.state_db,self.activity,self.device_id,
            settings.qdrant_url,settings.qdrant_collection,settings.qdrant_api_key) if hasattr(store,"fleet_snapshot_base") else None
        self.conflicts = ConflictService(self.state_db, self.activity)
        self.sync = SyncService(store, self.memories, self.outbox, self.state_db, self.activity, self.cloud,
            self.device_id, settings.embedding_dimension, snapshots=self.snapshots, conflicts=self.conflicts)
        self._background: set[asyncio.Task] = set()
        self._manual_runs: set[asyncio.Task] = set()

    async def start(self):
        """Reconcile metadata and recover uploads interrupted by a process restart."""
        await self.memories.reconcile()
        # Keep owned services aligned if a recovery workflow reopened the control DB.
        self.sync.store = self.store
        self.sync.memories = self.memories
        self.sync.outbox = self.outbox
        self.sync.db = self.state_db
        self.sync.activity = self.activity
        self.sync.conflicts = self.conflicts
        self.conflicts.db = self.state_db
        self.conflicts.activity = self.activity
        self.connectivity.db = self.state_db
        self.connectivity.activity = self.activity
        self.sync.recover_interrupted()
        if self.snapshots is not None:
            self.snapshots.store = self.store
            self.snapshots.db = self.state_db
            self.snapshots.activity = self.activity
            self.snapshots.reconcile_checkpoint()
        self.activity.append(ActivityEvent(event_type="DEVICE_STARTED", device_id=self.device_id,
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            message="Edge device runtime started"))

    def start_background(self):
        if self._background:
            return
        self._background = {
            asyncio.create_task(self._connectivity_loop(), name="edge-connectivity-monitor"),
            asyncio.create_task(self._sync_loop(), name="edge-sync-worker"),
        }

    async def _connectivity_loop(self):
        while True:
            try:
                await self._blocking(self.connectivity.run_once)
            except Exception:
                # Cloud status cannot take down the edge API; the next poll retries.
                pass
            await asyncio.sleep(self.connectivity_interval_seconds)

    @staticmethod
    async def _blocking(function, *args):
        job = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(job)
        except asyncio.CancelledError:
            # Cancelling an asyncio wrapper does not stop its worker thread. Keep
            # the runtime resources alive until the bounded I/O call has finished.
            await job
            raise

    async def _sync_loop(self):
        while True:
            try:
                await self.sync.run_once()
            except Exception:
                # The durable outbox remains available for the next worker iteration.
                pass
            await asyncio.sleep(self.sync_interval_seconds)

    def trigger_sync(self) -> bool:
        for task in tuple(self._manual_runs):
            if task.done():
                self._manual_runs.discard(task)
        if any(not task.done() for task in self._manual_runs):
            return False
        task = asyncio.create_task(self.sync.run_once(), name="edge-manual-sync")
        self._manual_runs.add(task)
        return True

    async def close(self):
        tasks = tuple(self._background | self._manual_runs)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if self.snapshots is not None:
                await self.snapshots.close()
        finally:
            try:
                self.store.close()
            finally:
                try:
                    self.state_db.close()
                finally:
                    try:
                        close = getattr(self.embedding_service, "close", None)
                        if close is not None:
                            await close()
                    finally:
                        close_remote = getattr(self.cloud, "close", None)
                        if close_remote is not None:
                            close_remote()
