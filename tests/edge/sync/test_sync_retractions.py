import asyncio
import json
from datetime import datetime, timezone

from app.edge.memory.models import CreateMemory, MemoryType, SyncState
from app.edge.memory.service import MemoryService
from app.edge.memory.store import StoredPoint
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox
from app.edge.sync.service import SyncService
from app.edge.sync.snapshot import FleetRefreshResult


class Store:
    def __init__(self):
        self.points = {}
        self.fleet = {}

    def upsert(self, point): self.points[point.id] = point
    def retrieve(self, point_id): return self.points.get(point_id)
    def retrieve_fleet(self, point_id): return self.fleet.get(point_id)
    def list_points(self): return list(self.points.values())
    def list_fleet_points(self): return list(self.fleet.values())
    def embed_bm25_document(self, _): return {"indices": [1], "values": [1.0]}


class Embeddings:
    async def embed_with_context(self, *_): return [1.0, 0.0, 0.0, 0.0]


class Remote:
    def __init__(self): self.points = {}; self.uploaded_payloads = []; self.delete_requests = []
    def health(self): return "ONLINE"
    def ensure_collection(self, _): pass
    def upsert_point(self, point):
        self.points[point.id] = point
        self.uploaded_payloads.append(dict(point.payload))
    def delete_points(self, point_ids):
        self.delete_requests.append(tuple(point_ids))
        for point_id in point_ids: self.points.pop(point_id, None)


class Snapshots:
    def __init__(self, store, remote, db): self.store, self.remote, self.db = store, remote, db
    async def refresh(self):
        self.store.fleet = dict(self.remote.points)
        now = datetime.now(timezone.utc).isoformat()
        metadata = {"generation": "gen-retracted", "refresh_id": "refresh-retracted", "timestamp": now, "kind": "partial"}
        with self.db.transaction() as conn:
            conn.execute("INSERT INTO sync_checkpoints(checkpoint_id,value,updated_at) VALUES('fleet',?,?) "
                         "ON CONFLICT(checkpoint_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                         (json.dumps(metadata), now))
        return FleetRefreshResult("COMPLETED", metadata["generation"], metadata["refresh_id"])


def setup(tmp_path):
    store, db = Store(), EdgeStateDB(tmp_path / "state.db")
    activity, outbox = ActivityLog(db), SyncOutbox(db)
    memories, remote = MemoryService(store, Embeddings(), db), Remote()
    snapshots = Snapshots(store, remote, db)
    sync = SyncService(store, memories, outbox, db, activity, remote, "robot-1", embedding_dimension=4, snapshots=snapshots)
    return store, db, activity, outbox, memories, remote, snapshots, sync


def test_tombstone_retracts_only_old_remote_ids_and_preserves_local_history_after_restart(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = setup(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe pump procedure", memory_type=MemoryType.LEARNED_FACT))
        first = await sync.run_once()
        assert first.uploaded == 1 and first.synchronized == 1
        assert record.memory_id in remote.points and record.memory_id in store.fleet

        deleted = await memories.tombstone(record.logical_id)
        assert deleted.is_deleted and deleted.sync_state is SyncState.LOCAL_ONLY
        second = await sync.run_once()

        assert record.memory_id not in remote.points
        assert record.memory_id not in store.fleet
        assert remote.delete_requests == [(record.memory_id,)]
        assert [payload["memory_id"] for payload in remote.uploaded_payloads] == [record.memory_id]
        assert deleted.memory_id not in json.dumps(remote.uploaded_payloads)
        assert not any(payload.get("is_deleted") for payload in remote.uploaded_payloads)
        assert memories.list() == []
        assert [entry.revision for entry in memories.history(record.logical_id)] == [1, 2]

        restarted = SyncService(store, memories, outbox, db, activity, remote, "robot-1", embedding_dimension=4, snapshots=snapshots)
        await restarted.run_once()
        assert remote.delete_requests == [(record.memory_id,)]
        assert [entry.memory_id for entry in memories.history(record.logical_id)] == [record.memory_id, deleted.memory_id]

    asyncio.run(run())


def test_never_uploaded_local_only_memory_creates_no_remote_retraction(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = setup(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="private local observation", memory_type=MemoryType.OBSERVATION))
        await memories.tombstone(record.logical_id)
        await sync.run_once()
        assert remote.uploaded_payloads == []
        assert remote.delete_requests == []

    asyncio.run(run())


def test_retraction_survives_network_failure_and_retries_after_restart(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = setup(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe valve note", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        await memories.tombstone(record.logical_id)
        real_delete, calls = remote.delete_points, []

        def flaky(ids):
            calls.append(ids)
            if len(calls) == 1:
                raise ConnectionError("offline")
            real_delete(ids)

        remote.delete_points = flaky
        failed = await sync.run_once()
        assert failed.status == "DEGRADED" and record.memory_id in remote.points
        restarted = SyncService(store, memories, outbox, db, activity, remote, "robot-1", embedding_dimension=4, snapshots=snapshots)
        await restarted.run_once()
        assert record.memory_id not in remote.points and record.memory_id not in store.fleet
        assert len(calls) == 2

    asyncio.run(run())


def test_delete_after_local_cleanup_restores_owned_copy_and_preserves_history(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = setup(tmp_path)
    store.delete_local = lambda memory_id: store.points.pop(memory_id, None)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe cleaned note", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        assert sync.cleanup_confirmed_local(datetime.now(timezone.utc).timestamp() + 1) == 1
        assert store.retrieve(record.memory_id) is None
        deleted = await memories.tombstone(record.logical_id)
        await sync.run_once()
        assert remote.delete_requests == [(record.memory_id,)]
        assert [entry.memory_id for entry in memories.history(record.logical_id)] == [record.memory_id, deleted.memory_id]

    asyncio.run(run())
