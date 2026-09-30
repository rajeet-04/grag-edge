import asyncio
import json
from datetime import datetime, timezone

from app.edge.memory.models import CreateMemory, MemoryType, SyncState
from app.edge.memory.service import MemoryService
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox
from app.edge.sync.service import SyncService
from app.edge.sync.snapshot import FleetRefreshResult


class Store:
    def __init__(self): self.points={}; self.fleet={}
    def upsert(self,point): self.points[point.id]=point
    def retrieve(self,key): return self.points.get(key)
    def retrieve_fleet(self,key): return self.fleet.get(key)
    def list_points(self): return list(self.points.values())
    def list_fleet_points(self): return list(self.fleet.values())
    def embed_bm25_document(self,_): return {"indices":[1],"values":[1.]}


class Embeddings:
    async def embed_with_context(self,*_): return [1.,0.,0.,0.]


class Remote:
    def __init__(self): self.points={}
    def ensure_collection(self,_): pass
    def upsert_point(self,point): self.points[point.id]=point


class Snapshots:
    def __init__(self,store,remote,db): self.store=store; self.remote=remote; self.db=db; self.publish=False; self.fail=False; self.calls=0
    async def refresh(self):
        self.calls+=1
        if self.fail: raise ValueError("snapshot rejected")
        if self.publish: self.store.fleet=dict(self.remote.points)
        now=datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute("INSERT INTO sync_checkpoints(checkpoint_id,value,updated_at) VALUES('fleet',?,?) "
                "ON CONFLICT(checkpoint_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (json.dumps({"generation":"generation-B","refresh_id":"refresh-B","timestamp":now,"kind":"partial"}),now))
        return FleetRefreshResult("COMPLETED","generation-B","refresh-B")
    def reconcile_checkpoint(self): pass


def setup(tmp_path):
    store=Store(); db=EdgeStateDB(tmp_path/"state.db"); activity=ActivityLog(db); outbox=SyncOutbox(db)
    memories=MemoryService(store,Embeddings(),db); remote=Remote(); snapshots=Snapshots(store,remote,db)
    sync=SyncService(store,memories,outbox,db,activity,remote,"robot",embedding_dimension=4,snapshots=snapshots)
    return store,db,activity,outbox,memories,remote,snapshots,sync


def test_uploaded_revision_waits_for_fleet_content_confirmation_and_completes_once(tmp_path):
    store,db,activity,outbox,memories,remote,snapshots,sync=setup(tmp_path)
    async def run():
        record=await memories.create(CreateMemory(content="fleet learned fact",memory_type=MemoryType.LEARNED_FACT))
        first=await sync.run_once()
        assert first.uploaded==1 and memories.get(record.memory_id).sync_state is SyncState.SNAPSHOT_PENDING
        assert not [e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"]
        from app.edge.memory.store import StoredPoint
        acknowledged=remote.points[record.memory_id]
        store.fleet[record.memory_id]=StoredPoint(acknowledged.id,acknowledged.dense,acknowledged.sparse,{**acknowledged.payload,"content_hash":"mismatch"})
        await sync.run_once()
        assert memories.get(record.memory_id).sync_state is SyncState.SNAPSHOT_PENDING
        snapshots.publish=True
        result=await sync.run_once()
        assert result.synchronized==1
        assert memories.get(record.memory_id).sync_state is SyncState.SYNCHRONIZED
        assert outbox.all()[0].status=="SYNCHRONIZED"
        sync.recover_interrupted()
        await sync.run_once()
        assert memories.get(record.memory_id).sync_state is SyncState.SYNCHRONIZED
        assert len([e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"])==1
        assert sync.history(10)[0]["status"]=="SYNCHRONIZED"
    asyncio.run(run())


def test_failed_snapshot_preserves_pending_ack_and_restart_completes_without_reupload(tmp_path):
    store,db,activity,outbox,memories,remote,snapshots,sync=setup(tmp_path)
    async def run():
        record=await memories.create(CreateMemory(content="learned safe procedure",memory_type=MemoryType.LEARNED_FACT))
        snapshots.fail=True
        result=await sync.run_once()
        assert result.status=="DEGRADED"
        assert memories.get(record.memory_id).sync_state is SyncState.SNAPSHOT_PENDING
        assert len(remote.points)==1
        sync.recover_interrupted()
        snapshots.fail=False; snapshots.publish=True
        restarted=SyncService(store,memories,outbox,db,activity,remote,"robot",embedding_dimension=4,snapshots=snapshots)
        result=await restarted.run_once()
        assert result.uploaded==0 and result.synchronized==1
        assert len(remote.points)==1
        assert len([e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"])==1
    asyncio.run(run())


def test_batch_completion_is_one_event_after_every_acknowledged_revision_present(tmp_path):
    store,db,activity,outbox,memories,remote,snapshots,sync=setup(tmp_path)
    async def run():
        records=[await memories.create(CreateMemory(content=f"learned fleet fact {i}",memory_type=MemoryType.LEARNED_FACT)) for i in range(2)]
        await sync.run_once()
        store.fleet[records[0].memory_id]=remote.points[records[0].memory_id]
        await sync.run_once()
        assert not [e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"]
        snapshots.publish=True
        result=await sync.run_once()
        assert result.synchronized==2
        assert len([e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"])==1
        assert all(memories.get(r.memory_id).sync_state is SyncState.SYNCHRONIZED for r in records)
    asyncio.run(run())


def test_no_uploads_still_bootstrap_and_refresh_fleet(tmp_path):
    store,db,activity,outbox,memories,remote,snapshots,sync=setup(tmp_path)
    assert asyncio.run(sync.run_once()).uploaded==0
    assert snapshots.calls==1


def test_refresh_without_durable_checkpoint_never_synchronizes_acknowledged_memory(tmp_path):
    store,db,activity,outbox,memories,remote,snapshots,sync=setup(tmp_path)
    async def uncheckpointed():
        store.fleet=dict(remote.points)
        return FleetRefreshResult("COMPLETED","generation-B","refresh-B")
    snapshots.refresh=uncheckpointed
    async def run():
        record=await memories.create(CreateMemory(content="fleet fact checkpoint needed",memory_type=MemoryType.LEARNED_FACT))
        result=await sync.run_once()
        assert result.status=="DEGRADED"
        assert memories.get(record.memory_id).sync_state is SyncState.SNAPSHOT_PENDING
        assert not [e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"]
    asyncio.run(run())


def test_completion_checkpoint_states_and_event_are_one_transaction(tmp_path):
    store,db,activity,outbox,memories,remote,snapshots,sync=setup(tmp_path)
    async def run():
        record=await memories.create(CreateMemory(content="learned transaction safety",memory_type=MemoryType.LEARNED_FACT))
        snapshots.publish=True
        with db.transaction() as conn:
            conn.execute("CREATE TRIGGER deny_sync_completion BEFORE INSERT ON activity_events WHEN NEW.event_type='SYNC_COMPLETED' BEGIN SELECT RAISE(ABORT,'completion interrupted'); END")
        result=await sync.run_once()
        assert result.status=="DEGRADED"
        assert memories.get(record.memory_id).sync_state is SyncState.SNAPSHOT_PENDING
        assert outbox.all()[0].status=="SNAPSHOT_PENDING"
        assert sync.history(10)[0]["status"]=="SNAPSHOT_PENDING"
        with db.transaction() as conn: conn.execute("DROP TRIGGER deny_sync_completion")
        result=await sync.run_once()
        assert result.synchronized==1
        assert memories.get(record.memory_id).sync_state is SyncState.SYNCHRONIZED
        assert len([e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"])==1
    asyncio.run(run())
