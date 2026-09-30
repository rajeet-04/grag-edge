"""P07 deferred items M6, M7, N3, N4 (tests first; each observed RED before the fix)."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.edge.conflicts.service import ConflictService
from app.edge.memory.models import CreateMemory, MemoryType, ReviseMemory, SyncState
from app.edge.memory.store import StoredPoint
from test_p07_review_regressions import fresh

PEER1 = "00000000-0000-0000-0000-0000000000a1"
PEER2 = "00000000-0000-0000-0000-0000000000a2"
PEER3 = "00000000-0000-0000-0000-0000000000a3"


def put_fleet(remote, template, memory_id, content, revision, parent, device="robot-2"):
    record = template.model_copy(update={
        "memory_id": memory_id, "content": content, "content_hash": "h-" + memory_id, "device_id": device,
        "revision": revision, "parent_revision": parent})
    remote.points[memory_id] = StoredPoint(memory_id, [1, 0, 0, 0], {"indices": [1], "values": [1.0]},
                                           {"record_type": "memory", **record.model_dump(mode="json")})
    return record


def enable_cleanup(store):
    store.delete_local = lambda memory_id: store.points.pop(memory_id, None)


def cutoff():
    return datetime.now(timezone.utc).timestamp() + 1


# ---- M6 -----------------------------------------------------------------

def test_m6_ownership_restore_picks_owned_candidate_not_fleet_maximum(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    enable_cleanup(store)

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        assert sync.cleanup_confirmed_local(cutoff()) == 1
        # A peer branch with a HIGHER revision reaches the fleet; it is not ours.
        put_fleet(remote, v1, PEER1, "peer v3", 3, 2)
        await snapshots.refresh()
        revised = await memories.revise(v1.logical_id, ReviseMemory(content="own v2", parent_revision=1))
        assert revised.parent_revision == 1 and revised.revision == 2

    asyncio.run(run())


def test_m6_tombstone_restores_owned_candidate_when_peer_revision_is_higher(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    enable_cleanup(store)

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        sync.cleanup_confirmed_local(cutoff())
        put_fleet(remote, v1, PEER1, "peer v2", 2, 1)
        await snapshots.refresh()
        tomb = await memories.tombstone(v1.logical_id)
        assert tomb.is_deleted and tomb.parent_revision == 1

    asyncio.run(run())


# ---- M7 -----------------------------------------------------------------

def test_m7_sync_cleans_confirmed_local_copy_after_synchronization(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    enable_cleanup(store)
    sync.cleanup_confirmed = True

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        result = await sync.run_once()
        assert result.synchronized == 1
        assert v1.memory_id not in store.points and v1.memory_id in store.fleet
        assert [r.memory_id for r in memories.list()] == [v1.memory_id]

    asyncio.run(run())


def test_m7_default_off_keeps_local_copy(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    enable_cleanup(store)

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        assert v1.memory_id in store.points

    asyncio.run(run())


def test_m7_open_conflict_blocks_cleanup(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    enable_cleanup(store)

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        local2 = await memories.revise(v1.logical_id, ReviseMemory(content="local v2", parent_revision=1))
        put_fleet(remote, local2, PEER1, "peer v2", 2, 1)
        await snapshots.refresh()
        sync.cleanup_confirmed = True
        await sync.run_once()
        assert len(sync.conflicts.list_open()) == 1
        assert v1.memory_id in store.points and local2.memory_id in store.points

    asyncio.run(run())


def test_m7_pending_retraction_blocks_cleanup(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    enable_cleanup(store)

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        await memories.tombstone(v1.logical_id)

        def offline(ids):
            raise ConnectionError("offline")

        remote.delete_points = offline
        sync.cleanup_confirmed = True
        result = await sync.run_once()
        assert result.status == "DEGRADED"
        assert v1.memory_id in store.points and v1.memory_id in store.fleet

    asyncio.run(run())


# ---- N3 -----------------------------------------------------------------

def test_n3_unprovable_child_does_not_hide_sibling_tips(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        local2 = await memories.revise(v1.logical_id, ReviseMemory(content="local v2", parent_revision=1))
        # Two peer siblings at revision 2 and a revision-3 child of only one of them.
        put_fleet(remote, local2, PEER1, "peer A v2", 2, 1, "robot-2")
        put_fleet(remote, local2, PEER2, "peer B v2", 2, 1, "robot-3")
        put_fleet(remote, local2, PEER3, "peer B v3", 3, 2, "robot-3")
        await snapshots.refresh()
        await sync.run_once()
        fleet_ids = {c.fleet_memory_id for c in sync.conflicts.list_open()}
        assert PEER1 in fleet_ids, fleet_ids

    asyncio.run(run())


# ---- N4 -----------------------------------------------------------------

def test_n4_memory_without_local_head_is_conflict_scanned_and_resolvable(tmp_path):
    store, db, activity, outbox, memories, remote, snapshots, sync = fresh(tmp_path)
    enable_cleanup(store)

    async def run():
        v1 = await memories.create(CreateMemory(content="fleet safe proc v1", memory_type=MemoryType.LEARNED_FACT))
        await sync.run_once()
        v2 = await memories.revise(v1.logical_id, ReviseMemory(content="own v2", parent_revision=1))
        await sync.run_once()
        assert sync.cleanup_confirmed_local(cutoff()) == 1
        assert [p.id for p in store.list_points()] == [v1.memory_id]  # superseded v1 stays as local history
        put_fleet(remote, v2, PEER1, "peer v2", 2, 1)
        await snapshots.refresh()
        await sync.run_once()
        (conflict,) = sync.conflicts.list_open()
        assert conflict.local_memory_id == v2.memory_id and conflict.fleet_memory_id == PEER1
        resolved = await sync.conflicts.resolve(conflict.conflict_id, "MERGE", memories, "merged text")
        assert resolved.status == "RESOLVED"
        assert memories.get(resolved.resolution_memory_id).content == "merged text"

    asyncio.run(run())
