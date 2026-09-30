import asyncio
from pathlib import Path

import httpx
import pytest

from app.edge.sync.snapshot import FleetSnapshotService
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.state.sqlite import EdgeStateDB
from app.edge.state.activity import ActivityLog


class SnapshotStore:
    def __init__(self): self.metadata = None; self.downloads = []
    def fleet_snapshot_metadata(self): return self.metadata
    def replace_fleet_from_snapshot(self, path):
        data = path.read_bytes()
        if data != b"valid snapshot": raise ValueError("invalid snapshot")
        self.downloads.append(data)
        self.metadata = {"generation": "test-generation", "refresh_id": "test-refresh", "timestamp": "2026-09-30T00:00:00+00:00", "kind": "full"}


def service(tmp_path, handler, store=None):
    db = EdgeStateDB(tmp_path / "state.db")
    store = store or SnapshotStore()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FleetSnapshotService(store, db, ActivityLog(db), "robot", "http://cloud", "fleet", client=client), store, db


def test_bootstrap_streams_full_snapshot_once_despite_existing_empty_fleet(tmp_path):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, content=b"valid snapshot")
    sync, store, db = service(tmp_path, handle)
    async def run():
        result = await sync.bootstrap_if_missing()
        assert result.status == "COMPLETED"
        assert (await sync.bootstrap_if_missing()).status == "UNCHANGED"
        assert store.downloads == [b"valid snapshot"]
        assert requests[0].method == "GET"
        assert requests[0].url.path == "/collections/fleet/shards/0/snapshot"
        assert db._connection.execute("SELECT value FROM sync_checkpoints WHERE checkpoint_id='fleet'").fetchone()
        await sync.close()
    asyncio.run(run())


def test_invalid_download_never_commits_checkpoint(tmp_path):
    sync, store, db = service(tmp_path, lambda _: httpx.Response(200, content=b"invalid"))
    async def run():
        with pytest.raises(ValueError): await sync.bootstrap_if_missing()
        assert store.metadata is None
        assert db._connection.execute("SELECT COUNT(*) FROM sync_checkpoints").fetchone()[0] == 0
        assert not list(tmp_path.glob("*.part"))
        await sync.close()
    asyncio.run(run())


def test_native_invalid_full_snapshot_and_orphan_restart_preserve_empty_fleet(tmp_path):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
    store.open()
    bad = tmp_path / "bad.snapshot"
    bad.write_bytes(b"invalid archive")
    with pytest.raises(Exception): store.replace_fleet_from_snapshot(bad)
    assert store.list_fleet_points() == []
    store.close()
    (tmp_path / "fleet-generations" / "orphan").mkdir(parents=True)
    reopened = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 4)
    reopened.open()
    assert reopened.fleet_snapshot_metadata() is None
    assert reopened.list_fleet_points() == []
    reopened.close()
