import asyncio
import io
import json
import tarfile
import threading

import httpx
import pytest

from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.store import StoredPoint
from app.edge.sync.snapshot import FleetSnapshotService
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from uuid import uuid4


class Store:
    def __init__(self):
        self.metadata = {"generation": "A", "refresh_id": "first", "timestamp": "2026-09-30T00:00:00+00:00", "kind": "full"}
        self.manifest = {"segment": {"files": {"file": 7}}}
        self.applied = []
    def fleet_snapshot_metadata(self): return self.metadata
    def fleet_manifest(self): return self.manifest
    def fleet_snapshot_base(self): return self.manifest, self.metadata
    def stage_and_apply_fleet_snapshot(self, path, **kwargs):
        if path.read_bytes() == b"bad": raise ValueError("invalid partial")
        self.applied.append(path.read_bytes())
        self.metadata = {**self.metadata, "generation": "B", "refresh_id": "second", "kind": "partial"}


def test_partial_posts_raw_manifest_and_completes_once_only_after_publish(tmp_path):
    requests = []
    def handler(request): requests.append(request); return httpx.Response(200, content=b"partial")
    db = EdgeStateDB(tmp_path / "state.db"); activity = ActivityLog(db); store = Store()
    sync = FleetSnapshotService(store, db, activity, "robot", "http://cloud", "fleet", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async def run():
        result = await sync.refresh()
        assert result.status == "COMPLETED" and result.generation == "B"
        assert json.loads(requests[0].content) == store.manifest
        assert requests[0].url.path == "/collections/fleet/shards/0/snapshot/partial/create"
        assert requests[0].method == "POST"
        sync.reconcile_checkpoint()
        assert [e.event_type for e in activity.list(20)].count("FLEET_REFRESH_COMPLETED") == 1
        assert [e.event_type for e in activity.list(20)].count("FLEET_REFRESH_STARTED") == 1
        await sync.close()
    asyncio.run(run())


def test_failed_partial_has_no_completion_or_new_checkpoint(tmp_path):
    db = EdgeStateDB(tmp_path / "state.db"); activity = ActivityLog(db); store = Store()
    sync = FleetSnapshotService(store, db, activity, "robot", "http://cloud", "fleet", client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"bad"))))
    async def run():
        with pytest.raises(ValueError): await sync.refresh()
        assert store.metadata["generation"] == "A"
        assert [e.event_type for e in activity.list(20)] == ["FLEET_REFRESH_STARTED"]
        assert db._connection.execute("SELECT COUNT(*) FROM sync_checkpoints").fetchone()[0] == 0
        await sync.close()
    asyncio.run(run())


def test_native_late_apply_failure_does_not_damage_active_fleet_or_local(tmp_path):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4); store.open()
    manifest = store.fleet_manifest()
    snapshot = tmp_path / "late-invalid.snapshot"
    with tarfile.open(snapshot, "w") as tar:
        entry = tarfile.TarInfo("segments"); entry.type = tarfile.DIRTYPE; entry.mode = 0o644; tar.addfile(entry)
    with pytest.raises(Exception): store.stage_and_apply_fleet_snapshot(snapshot)
    assert store.fleet_manifest() == manifest
    assert store.list_fleet_points() == []
    point = StoredPoint(str(uuid4()), [1., 0., 0., 0.], None, {"content": "local available"})
    store.upsert(point); assert store.retrieve(point.id) == point
    store.close()
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4); store.open()
    assert store.list_fleet_points() == [] and store.retrieve(point.id) == point
    store.close()


def test_local_write_and_event_loop_continue_while_snapshot_download_waits(tmp_path):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4); store.open()
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(_): started.set(); await release.wait(); return httpx.Response(500)
    db = EdgeStateDB(tmp_path / "state.db")
    sync = FleetSnapshotService(store, db, ActivityLog(db), "robot", "http://cloud", "fleet", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async def run():
        task = asyncio.create_task(sync.refresh()); await started.wait()
        point = StoredPoint(str(uuid4()), [1.,0.,0.,0.], None, {"content": "robot observation"})
        store.upsert(point); assert store.retrieve(point.id) == point
        release.set()
        with pytest.raises(httpx.HTTPStatusError): await task
        await sync.close()
    asyncio.run(run()); store.close()


def test_local_native_write_continues_while_clone_holds_fleet_lock(tmp_path, monkeypatch):
    import app.edge.memory.qdrant_store as adapter
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4); store.open()
    started, release = threading.Event(), threading.Event()
    copytree = adapter.shutil.copytree
    def blocked_copy(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return copytree(*args, **kwargs)
    monkeypatch.setattr(adapter.shutil, "copytree", blocked_copy)
    bad=tmp_path/"bad.snapshot"; bad.write_bytes(b"bad")
    async def run():
        task=asyncio.create_task(asyncio.to_thread(store.stage_and_apply_fleet_snapshot,bad))
        assert await asyncio.to_thread(started.wait, 5)
        point=StoredPoint(str(uuid4()),[1.,0.,0.,0.],None,{"content":"during clone"})
        await asyncio.wait_for(asyncio.to_thread(store.upsert,point),1)
        assert store.retrieve(point.id) == point
        release.set()
        with pytest.raises(Exception): await task
    asyncio.run(run()); store.close()


def test_cancelled_native_work_waits_for_worker_before_closing_or_deleting_download(tmp_path):
    store=Store(); started,release=threading.Event(),threading.Event()
    def blocked_apply(path, **kwargs):
        started.set(); assert release.wait(5); assert path.exists()
        store.metadata={**store.metadata,"generation":"B","refresh_id":"cancelled-but-published"}
    store.stage_and_apply_fleet_snapshot=blocked_apply
    db=EdgeStateDB(tmp_path/"state.db"); activity=ActivityLog(db)
    sync=FleetSnapshotService(store,db,activity,"robot","http://cloud","fleet",client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b"partial"))))
    async def run():
        task=asyncio.create_task(sync.refresh()); assert await asyncio.to_thread(started.wait,5)
        task.cancel(); await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert [e.event_type for e in activity.list(10)].count("FLEET_REFRESH_COMPLETED") == 1
        await sync.close()
    asyncio.run(run())


def test_stale_download_base_is_rejected_before_native_apply(tmp_path):
    store=QdrantEdgeStore(tmp_path/"local",tmp_path/"fleet",4); store.open()
    bad=tmp_path/"bad.snapshot"; bad.write_bytes(b"bad")
    with pytest.raises(RuntimeError,match="base generation changed"):
        store.stage_and_apply_fleet_snapshot(bad,expected_generation="already-replaced")
    assert store.list_fleet_points()==[]
    store.close()
