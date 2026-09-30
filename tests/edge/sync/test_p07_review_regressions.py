"""Retained regressions from the fresh P04-P07 boundary review."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.edge.conflicts.service import ConflictResolutionError, ConflictService
from app.edge.memory.models import CreateMemory, MemoryType, ReviseMemory, SyncState
from app.edge.memory.store import StoredPoint
from test_sync_retractions import setup


def fresh(tmp_path):
    parts = setup(tmp_path)
    store, db, activity, outbox, memories, remote, snapshots, sync = parts
    sync.conflicts = ConflictService(db, activity)
    return parts


def other_branch(remote, local, memory_id, content):
    record = local.model_copy(update={"memory_id": memory_id, "content": content, "content_hash": "h-" + memory_id, "device_id": "robot-2"})
    remote.points[memory_id] = StoredPoint(memory_id, [1, 0, 0, 0], {"indices": [1], "values": [1.0]},
                                           {"record_type": "memory", **record.model_dump(mode="json")})
    return record


def jobs(db):
    return [json.loads(r["value"]) for r in db._connection.execute("SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-retraction:%'")]


def test_retraction_is_not_completed_when_fleet_refresh_failed(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe A", memory_type=MemoryType.LEARNED_FACT))
        good_refresh = snapshots.refresh

        async def offline():
            raise ConnectionError("snapshot offline")

        snapshots.refresh = offline
        await sync.run_once()
        await memories.tombstone(record.logical_id)
        result = await sync.run_once()
        assert result.refresh_error and [j["status"] for j in jobs(db)] != ["COMPLETED"]
        snapshots.refresh = good_refresh
        await sync.run_once()
        assert [j["status"] for j in jobs(db)] == ["COMPLETED"] and record.memory_id not in store.fleet

    asyncio.run(run())


def test_resolution_after_local_branch_moved_on_is_rejected_without_stray_point(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        local2 = await memories.revise(record.logical_id, ReviseMemory(content="local v2", parent_revision=1))
        other_branch(remote, local2, "00000000-0000-0000-0000-0000000000f2", "fleet v2")
        await snapshots.refresh()
        await sync.run_once()
        conflict = sync.conflicts.list_open()[0]
        await memories.revise(record.logical_id, ReviseMemory(content="local v3", parent_revision=2))
        before = {p.id for p in store.list_points()}
        with pytest.raises(ConflictResolutionError):
            await sync.conflicts.resolve(conflict.conflict_id, "KEEP_LOCAL", memories)
        assert {p.id for p in store.list_points()} == before
        assert sync.conflicts.open_count() == 0
        await memories.reconcile()  # restart reconciliation still succeeds

    asyncio.run(run())


def test_revision_is_not_conflicted_with_its_own_cleaned_parent(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    store.delete_local = lambda memory_id: store.points.pop(memory_id, None)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        cutoff = datetime.now(timezone.utc).timestamp() + 1
        assert sync.cleanup_confirmed_local(cutoff) == 1
        local2 = await memories.revise(record.logical_id, ReviseMemory(content="fleet safe proc v2", parent_revision=1))
        sync.cleanup_confirmed_local(cutoff)
        result = await sync.run_once()
        assert result.uploaded == 1 and sync.conflicts.list_open() == []
        assert local2.memory_id in remote.points

    asyncio.run(run())


def test_divergence_is_detected_after_both_branches_uploaded(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        local2 = await memories.revise(record.logical_id, ReviseMemory(content="local v2", parent_revision=1))
        other_branch(remote, local2, "00000000-0000-0000-0000-0000000000f3", "other v2")
        await sync.run_once()
        await sync.run_once()
        assert local2.memory_id in store.fleet and "00000000-0000-0000-0000-0000000000f3" in store.fleet
        open_conflicts = sync.conflicts.list_open()
        assert len(open_conflicts) == 1 and open_conflicts[0].local_memory_id == local2.memory_id
        assert memories.get(local2.memory_id).sync_state is SyncState.CONFLICTED

    asyncio.run(run())


def test_merge_retry_with_different_content_is_rejected(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        local2 = await memories.revise(record.logical_id, ReviseMemory(content="local v2", parent_revision=1))
        other_branch(remote, local2, "00000000-0000-0000-0000-0000000000f4", "other v2")
        await snapshots.refresh()
        await sync.run_once()
        conflict = sync.conflicts.list_open()[0]
        first = await sync.conflicts.resolve(conflict.conflict_id, "MERGE", memories, "merged one")
        with pytest.raises(ConflictResolutionError):
            await sync.conflicts.resolve(conflict.conflict_id, "MERGE", memories, "merged two")
        assert memories.get(first.resolution_memory_id).content == "merged one"

    asyncio.run(run())


def device(tmp_path, name, remote):
    from app.edge.memory.service import MemoryService
    from app.edge.state.activity import ActivityLog
    from app.edge.state.sqlite import EdgeStateDB
    from app.edge.sync.outbox import SyncOutbox
    from app.edge.sync.service import SyncService
    from test_sync_retractions import Embeddings, Snapshots, Store
    store, db = Store(), EdgeStateDB(tmp_path / f"{name}.db")
    activity, outbox = ActivityLog(db), SyncOutbox(db)
    memories = MemoryService(store, Embeddings(), db)
    sync = SyncService(store, memories, outbox, db, activity, remote, name, embedding_dimension=4,
                       snapshots=Snapshots(store, remote, db), conflicts=ConflictService(db, activity))
    return store, memories, sync


def test_resolution_on_one_device_does_not_conflict_or_reopen_on_the_other(tmp_path):
    from test_sync_retractions import Remote
    remote = Remote()
    store_a, mem_a, sync_a = device(tmp_path, "a", remote)
    store_b, mem_b, sync_b = device(tmp_path, "b", remote)
    ids = dict(memory_id="00000000-0000-0000-0000-00000000000a", logical_id="00000000-0000-0000-0000-00000000000b")

    async def run():
        for mem in (mem_a, mem_b):
            await mem.create(CreateMemory(content="shared safe base", memory_type=MemoryType.LEARNED_FACT, **ids))
        await sync_a.run_once(); await sync_b.run_once()
        a2 = await mem_a.revise(ids["logical_id"], ReviseMemory(content="branch from a", parent_revision=1))
        b2 = await mem_b.revise(ids["logical_id"], ReviseMemory(content="branch from b", parent_revision=1))
        for sync in (sync_a, sync_b, sync_a, sync_b):
            await sync.run_once()
        assert len(sync_a.conflicts.list_open()) == 1 and len(sync_b.conflicts.list_open()) == 1
        resolved = await sync_a.conflicts.resolve(sync_a.conflicts.list_open()[0].conflict_id, "KEEP_LOCAL", mem_a)
        await sync_a.run_once(); await sync_b.run_once(); await sync_b.run_once()
        assert resolved.resolution_memory_id in store_b.fleet
        assert sync_a.conflicts.list_open() == []
        assert sync_b.conflicts.list_open() == []
        assert mem_b.get(b2.memory_id).sync_state is not SyncState.CONFLICTED

    asyncio.run(run())


def test_superseded_open_conflict_is_closed_by_scan(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)

    async def run():
        record = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        local2 = await memories.revise(record.logical_id, ReviseMemory(content="local v2", parent_revision=1))
        other_branch(remote, local2, "00000000-0000-0000-0000-0000000000f5", "other v2")
        await snapshots.refresh()
        await sync.run_once()
        assert len(sync.conflicts.list_open()) == 1
        await memories.revise(record.logical_id, ReviseMemory(content="local v3", parent_revision=2))
        await sync.run_once()
        assert [c.local_revision for c in sync.conflicts.list_open()] == [3]

    asyncio.run(run())
