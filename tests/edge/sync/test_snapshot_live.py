"""Opt-in real server/native binary format gate without publishing Qdrant ports.

QDRANT_LIVE_DOCKER_CONTAINER=grag-api uv run pytest .../test_snapshot_live.py -v
The configured container must reach qdrant-server:6333 on the cloud network.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import shutil
from uuid import uuid4

import httpx
import pytest

from app.edge.memory.models import MemoryRecord, MemoryType
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.store import MemoryOrigin
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.snapshot import FleetSnapshotService


_REMOTE = '''import json,sys,urllib.request,urllib.error
request=json.load(sys.stdin)
body=json.dumps(request["body"]).encode() if request.get("body") is not None else None
req=urllib.request.Request("http://qdrant-server:6333"+request["path"],data=body,method=request["method"],headers={"Content-Type":"application/json"})
try:
 response=urllib.request.urlopen(req, timeout=60)
except urllib.error.HTTPError as error:
 response=error
with response:
 sys.stdout.buffer.write(str(response.status).encode()+b"\\n"+response.read())
'''


class DockerCloud:
    def __init__(self, container): self.container = container; self.requests = []
    def request(self, method, path, body=None, with_status=False):
        self.requests.append((method, path, body))
        result = subprocess.run([os.environ.get("DOCKER_BIN") or shutil.which("docker") or "docker", "exec", "-i", self.container,
            "/app/.venv/bin/python", "-c", _REMOTE], input=json.dumps({"method":method,"path":path,"body":body}).encode(), capture_output=True, timeout=75, check=True)
        status, data = result.stdout.split(b"\n", 1)
        status = int(status)
        if status >= 400:
            raise RuntimeError(f"Cloud HTTP {status}: {data[:500]!r}")
        return (status, data) if with_status else data


class DockerTransport(httpx.AsyncBaseTransport):
    def __init__(self, cloud): self.cloud = cloud
    async def handle_async_request(self, request):
        body = json.loads(request.content) if request.content else None
        status, data = await asyncio.to_thread(self.cloud.request, request.method, request.url.path, body, True)
        return httpx.Response(status, content=data)


@pytest.mark.skipif(not os.getenv("QDRANT_LIVE_DOCKER_CONTAINER"), reason="requires opt-in cloud network helper")
def test_live_full_changed_partial_deleted_and_unchanged_roundtrip(tmp_path):
    cloud = DockerCloud(os.environ["QDRANT_LIVE_DOCKER_CONTAINER"])
    collection = "p06_native_" + uuid4().hex
    base = "/collections/" + collection
    schema = {"shard_number":1,"vectors":{"dense":{"size":768,"distance":"Cosine"}},"sparse_vectors":{"text":{"modifier":"idf"}}}
    cloud.request("PUT",base,schema)
    now = datetime.now(timezone.utc)
    def point(content):
        record = MemoryRecord(memory_id=str(uuid4()),logical_id=str(uuid4()),content=content,revision=1,
            created_at=now,updated_at=now,content_hash=hashlib.sha256(content.encode()).hexdigest(),memory_type=MemoryType.PROCEDURE)
        return {"id":record.memory_id,"vector":{"dense":[1.0]+[0.0]*767,"text":{"indices":[1],"values":[1.0]}},
                "payload":{**record.model_dump(mode="json"),"record_type":"memory"}}
    a,b=point("fleet procedure A"),point("fleet procedure B")
    store = QdrantEdgeStore(tmp_path/"local",tmp_path/"fleet",768); store.open()
    db = EdgeStateDB(tmp_path/"state.db"); activity=ActivityLog(db)
    sync=FleetSnapshotService(store,db,activity,"robot","http://cloud",collection,client=httpx.AsyncClient(transport=DockerTransport(cloud)))
    async def run():
        cloud.request("PUT",base+"/points?wait=true",{"points":[a]})
        await sync.bootstrap_if_missing()
        assert store.retrieve_fleet(a["id"]).payload["content"] == "fleet procedure A"
        assert store.query_dense([1.0]+[0.0]*767,10,MemoryOrigin.FLEET)[0].point_id == a["id"]
        manifest = store.fleet_manifest()
        # Exercise the version-specific late failure on a nonempty native base.
        late_invalid = tmp_path / "late-invalid.snapshot"
        with tarfile.open(late_invalid, "w") as archive:
            entry = tarfile.TarInfo("segments")
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o644
            archive.addfile(entry)
        with pytest.raises(Exception):
            store.stage_and_apply_fleet_snapshot(late_invalid)
        assert store.retrieve_fleet(a["id"]).payload["content"] == "fleet procedure A"
        assert store.fleet_manifest() == manifest
        cloud.request("PUT",base+"/points?wait=true",{"points":[b]})
        cloud.request("POST",base+"/points/delete?wait=true",{"points":[a["id"]]})
        await sync.refresh()
        assert store.retrieve_fleet(a["id"]) is None
        assert store.retrieve_fleet(b["id"]).payload["content"] == "fleet procedure B"
        partial = next(body for method,path,body in cloud.requests if path.endswith("/partial/create"))
        assert partial == manifest
        unchanged = await sync.refresh()
        assert [p.id for p in store.list_fleet_points()] == [b["id"]]
        expected_completions = 2 if unchanged.status == "UNCHANGED" else 3
        assert len([e for e in activity.list(100) if e.event_type=="FLEET_REFRESH_COMPLETED"]) == expected_completions
        await sync.close()
    try:
        asyncio.run(run())
        store.close()
        store = QdrantEdgeStore(tmp_path/"local",tmp_path/"fleet",768); store.open()
        assert store.retrieve_fleet(b["id"]) is not None
    finally:
        store.close(); db.close(); cloud.request("DELETE",base)


@pytest.mark.skipif(not os.getenv("QDRANT_LIVE_DOCKER_CONTAINER"), reason="requires opt-in cloud network helper")
def test_live_upload_partial_confirmation_and_durable_restart(tmp_path):
    from app.edge.memory.models import CreateMemory, SyncState
    from app.edge.memory.service import MemoryService
    from app.edge.sync.outbox import SyncOutbox
    from app.edge.sync.service import SyncService
    from app.edge.sync.server_client import CloudHealth, RemoteAck
    cloud=DockerCloud(os.environ["QDRANT_LIVE_DOCKER_CONTAINER"])
    collection="p06_lifecycle_"+uuid4().hex; base="/collections/"+collection
    cloud.request("PUT",base,{"shard_number":1,"vectors":{"dense":{"size":768,"distance":"Cosine"}},"sparse_vectors":{"text":{"modifier":"idf"}}})
    class Remote:
        def health(self): return CloudHealth.ONLINE
        def ensure_collection(self,_): pass
        def upsert_point(self,point):
            response=json.loads(cloud.request("PUT",base+"/points?wait=true",{"points":[{"id":point.id,"vector":{"dense":point.dense,"text":point.sparse},"payload":point.payload}]}))
            assert response["result"]["status"]=="completed"
            return RemoteAck(point.id,"completed")
    class Embeddings:
        async def embed_with_context(self,*_): return [1.0]+[0.0]*767
    store=QdrantEdgeStore(tmp_path/"local",tmp_path/"fleet",768); store.open()
    db=EdgeStateDB(tmp_path/"state.db"); activity=ActivityLog(db); outbox=SyncOutbox(db)
    remote=Remote(); memories=MemoryService(store,Embeddings(),db)
    snapshots=FleetSnapshotService(store,db,activity,"robot","http://cloud",collection,client=httpx.AsyncClient(transport=DockerTransport(cloud)))
    sync=SyncService(store,memories,outbox,db,activity,remote,"robot",embedding_dimension=768,snapshots=snapshots)
    async def run():
        # An empty full snapshot is a real committed bootstrap, then an upload
        # arrives through the subsequent partial snapshot on the native shard.
        await snapshots.bootstrap_if_missing()
        assert store.fleet_snapshot_metadata() is not None and store.list_fleet_points()==[]
        record=await memories.create(CreateMemory(content="live fleet maintenance fact",memory_type=MemoryType.LEARNED_FACT))
        result=await sync.run_once()
        assert result.uploaded==1 and result.synchronized==1
        assert memories.get(record.memory_id).sync_state is SyncState.SYNCHRONIZED
        assert store.retrieve_fleet(record.memory_id).payload["content_hash"]==record.content_hash
        assert sync.history(10)[0]["status"]=="SYNCHRONIZED"
        await sync.run_once()
        assert len([e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"])==1
        await snapshots.close()
        return record.memory_id
    try:
        memory_id=asyncio.run(run()); store.close(); db.close()
        store=QdrantEdgeStore(tmp_path/"local",tmp_path/"fleet",768); store.open()
        db=EdgeStateDB(tmp_path/"state.db"); activity=ActivityLog(db); outbox=SyncOutbox(db)
        memories=MemoryService(store,Embeddings(),db)
        sync=SyncService(store,memories,outbox,db,activity,remote,"robot",embedding_dimension=768)
        sync.recover_interrupted()
        assert memories.get(memory_id).sync_state is SyncState.SYNCHRONIZED
        assert len([e for e in activity.list(100) if e.event_type=="SYNC_COMPLETED"])==1
    finally:
        store.close(); db.close(); cloud.request("DELETE",base)


@pytest.mark.skipif(not os.getenv("QDRANT_LIVE_DOCKER_CONTAINER"), reason="requires opt-in cloud network helper")
def test_live_deletion_retracts_remote_point_and_confirms_fleet_absence(tmp_path):
    from app.edge.memory.models import CreateMemory
    from app.edge.memory.service import MemoryService
    from app.edge.sync.outbox import SyncOutbox
    from app.edge.sync.service import SyncService
    from app.edge.sync.server_client import CloudHealth, RemoteAck
    cloud=DockerCloud(os.environ["QDRANT_LIVE_DOCKER_CONTAINER"])
    collection="p07_retraction_"+uuid4().hex; base="/collections/"+collection
    cloud.request("PUT",base,{"shard_number":1,"vectors":{"dense":{"size":768,"distance":"Cosine"}},"sparse_vectors":{"text":{"modifier":"idf"}}})
    def remote_ids():
        found=json.loads(cloud.request("POST",base+"/points/scroll",{"limit":100,"with_payload":False}))
        return {str(p["id"]) for p in found["result"]["points"]}
    class Remote:
        def health(self): return CloudHealth.ONLINE
        def ensure_collection(self,_): pass
        def upsert_point(self,point):
            json.loads(cloud.request("PUT",base+"/points?wait=true",{"points":[{"id":point.id,"vector":{"dense":point.dense,"text":point.sparse},"payload":point.payload}]}))
            return RemoteAck(point.id,"completed")
        def delete_points(self,ids):
            cloud.request("POST",base+"/points/delete?wait=true",{"points":list(ids)})
    class Embeddings:
        async def embed_with_context(self,*_): return [1.0]+[0.0]*767
    store=QdrantEdgeStore(tmp_path/"local",tmp_path/"fleet",768); store.open()
    db=EdgeStateDB(tmp_path/"state.db"); activity=ActivityLog(db); outbox=SyncOutbox(db)
    memories=MemoryService(store,Embeddings(),db)
    snapshots=FleetSnapshotService(store,db,activity,"robot","http://cloud",collection,client=httpx.AsyncClient(transport=DockerTransport(cloud)))
    sync=SyncService(store,memories,outbox,db,activity,Remote(),"robot",embedding_dimension=768,snapshots=snapshots)
    async def run():
        await snapshots.bootstrap_if_missing()
        record=await memories.create(CreateMemory(content="live retractable maintenance fact",memory_type=MemoryType.LEARNED_FACT))
        assert (await sync.run_once()).synchronized==1
        assert remote_ids()=={record.memory_id} and store.retrieve_fleet(record.memory_id) is not None
        deleted=await memories.tombstone(record.logical_id)
        await sync.run_once()
        assert remote_ids()==set() and store.retrieve_fleet(record.memory_id) is None
        assert deleted.memory_id not in remote_ids()
        assert [r.memory_id for r in memories.history(record.logical_id)]==[record.memory_id,deleted.memory_id]
        assert all(job["status"]=="COMPLETED" for job in [json.loads(r["value"]) for r in db._connection.execute("SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-retraction:%'")])
        await snapshots.close()
    try:
        asyncio.run(run())
    finally:
        store.close(); db.close(); cloud.request("DELETE",base)
