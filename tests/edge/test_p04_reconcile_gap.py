"""Native restart regressions for Qdrant-first, SQLite-second writes."""
import asyncio
import sqlite3

import pytest

from app.edge.memory.models import CreateMemory, MemoryRecord, MemoryType, ReviseMemory, SyncState
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.runtime import EdgeRuntime


class Embeddings:
    async def embed_with_context(self, text, task_type):
        return [0.8, 0.6]

    async def embed_text(self, text):
        return [0.8, 0.6]

    async def close(self):
        pass


def _runtime(tmp_path):
    store = QdrantEdgeStore(tmp_path / "local", tmp_path / "fleet", 2)
    store.open()
    return EdgeRuntime(store, Embeddings(), tmp_path / "state.db")


def _fail_next_control_transaction(runtime):
    original = runtime.state_db.transaction

    def fail():
        raise sqlite3.OperationalError("injected control-plane outage")

    runtime.state_db.transaction = fail
    return original


def test_restart_reconciles_failed_root_write_followed_by_revision(tmp_path):
    async def scenario():
        runtime = _runtime(tmp_path)
        original = _fail_next_control_transaction(runtime)
        with pytest.raises(sqlite3.OperationalError):
            await runtime.memories.create(CreateMemory(content="learned maintenance fact", memory_type=MemoryType.LEARNED_FACT))
        runtime.state_db.transaction = original

        root = MemoryRecord.model_validate(runtime.store.list_points()[0].payload)
        revised = await runtime.memories.revise(root.logical_id, ReviseMemory(content="revised maintenance fact", parent_revision=1))
        assert revised.revision == 2 and revised.sync_state is SyncState.QUEUED
        await runtime.close()

        reopened = _runtime(tmp_path)
        await reopened.start()
        history = reopened.memories.history(root.logical_id)
        assert [item.revision for item in history] == [1, 2]
        assert history[0].sync_state is SyncState.SUPERSEDED
        assert history[1].sync_state is SyncState.QUEUED
        assert [item.memory_id for item in reopened.outbox.pending(10)] == [revised.memory_id]
        await reopened.start()
        assert [item.memory_id for item in reopened.outbox.pending(10)] == [revised.memory_id]
        await reopened.close()

    asyncio.run(scenario())


def test_restart_reconciles_failed_intermediate_revision_in_order(tmp_path):
    async def scenario():
        runtime = _runtime(tmp_path)
        root = await runtime.memories.create(CreateMemory(content="initial maintenance fact", memory_type=MemoryType.LEARNED_FACT))
        root_item = runtime.outbox.pending(10)[0]
        runtime.outbox.mark_uploading(root_item.id)
        runtime.outbox.mark_uploaded(root_item.id)
        original = _fail_next_control_transaction(runtime)
        with pytest.raises(sqlite3.OperationalError):
            await runtime.memories.revise(root.logical_id, ReviseMemory(content="intermediate failed", parent_revision=1))
        runtime.state_db.transaction = original

        latest = await runtime.memories.revise(root.logical_id, ReviseMemory(content="latest maintenance fact", parent_revision=2))
        assert latest.revision == 3
        await runtime.close()

        reopened = _runtime(tmp_path)
        await reopened.start()
        history = reopened.memories.history(root.logical_id)
        assert [item.revision for item in history] == [1, 2, 3]
        assert history[1].sync_state is SyncState.SUPERSEDED
        assert history[2].sync_state is SyncState.QUEUED
        all_items = reopened.outbox.all()
        assert [(item.revision, item.status) for item in all_items] == [(1, "UPLOADED"), (3, "QUEUED")]
        queue = reopened.outbox.pending(10)
        assert [item.revision for item in queue] == [3]
        await reopened.start()
        assert [(item.revision, item.status) for item in reopened.outbox.all()] == [(1, "UPLOADED"), (3, "QUEUED")]
        await reopened.close()

    asyncio.run(scenario())


def test_reconcile_does_not_queue_superseded_restricted_history(tmp_path):
    async def scenario():
        runtime = _runtime(tmp_path)
        root = await runtime.memories.create(CreateMemory(
            content="restricted maintenance fact", memory_type=MemoryType.LEARNED_FACT, sensitivity="restricted"
        ))
        original = _fail_next_control_transaction(runtime)
        with pytest.raises(sqlite3.OperationalError):
            await runtime.memories.revise(root.logical_id, ReviseMemory(content="restricted gap", parent_revision=1))
        runtime.state_db.transaction = original

        latest = await runtime.memories.revise(root.logical_id, ReviseMemory(content="restricted current", parent_revision=2))
        assert latest.sync_state is SyncState.LOCAL_ONLY
        await runtime.close()

        reopened = _runtime(tmp_path)
        await reopened.start()
        history = reopened.memories.history(root.logical_id)
        assert history[1].sync_state is SyncState.SUPERSEDED
        assert history[2].sync_state is SyncState.LOCAL_ONLY
        assert reopened.outbox.pending(10) == []
        await reopened.close()

    asyncio.run(scenario())
