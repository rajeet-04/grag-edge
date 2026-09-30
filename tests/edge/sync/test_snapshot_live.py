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


_REMOTE = '''import json,sys,urllib.request
request=json.load(sys.stdin)
body=json.dumps(request["body"]).encode() if request.get("body") is not None else None
req=urllib.request.Request("http://qdrant-server:6333"+request["path"],data=body,method=request["method"],headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req, timeout=60) as response:
 sys.stdout.buffer.write(response.read())
'''


class DockerCloud:
    def __init__(self, container): self.container = container; self.requests = []
    def request(self, method, path, body=None):
        self.requests.append((method, path, body))
        result = subprocess.run([os.environ.get("DOCKER_BIN") or shutil.which("docker") or "docker", "exec", "-i", self.container,
            "/app/.venv/bin/python", "-c", _REMOTE], input=json.dumps({"method":method,"path":path,"body":body}).encode(), capture_output=True, timeout=75, check=True)
        return result.stdout


class DockerTransport(httpx.AsyncBaseTransport):
    def __init__(self, cloud): self.cloud = cloud
    async def handle_async_request(self, request):
        body = json.loads(request.content) if request.content else None
        data = await asyncio.to_thread(self.cloud.request, request.method, request.url.path, body)
        return httpx.Response(200, content=data)


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
        cloud.request("PUT",base+"/points?wait=true",{"points":[b]})
        cloud.request("POST",base+"/points/delete?wait=true",{"points":[a["id"]]})
        await sync.refresh()
        assert store.retrieve_fleet(a["id"]) is None
        assert store.retrieve_fleet(b["id"]).payload["content"] == "fleet procedure B"
        partial = next(body for method,path,body in cloud.requests if path.endswith("/partial/create"))
        assert partial == manifest
        await sync.refresh()
        assert [p.id for p in store.list_fleet_points()] == [b["id"]]
        assert len([e for e in activity.list(100) if e.event_type=="FLEET_REFRESH_COMPLETED"]) == 3
        await sync.close()
    try:
        asyncio.run(run())
        store.close()
        store = QdrantEdgeStore(tmp_path/"local",tmp_path/"fleet",768); store.open()
        assert store.retrieve_fleet(b["id"]) is not None
    finally:
        store.close(); db.close(); cloud.request("DELETE",base)
