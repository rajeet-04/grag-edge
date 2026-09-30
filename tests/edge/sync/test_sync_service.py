import asyncio

import pytest

from app.edge.memory.models import CreateMemory, MemoryType, SyncState
from app.edge.memory.store import StoredPoint
from app.edge.memory.service import MemoryService
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox
from app.edge.sync.service import SyncService


class Store:
    def __init__(self): self.points = {}
    def upsert(self, point): self.points[point.id] = point
    def retrieve(self, point_id): return self.points.get(point_id)
    def list_points(self): return list(self.points.values())
    def retrieve_fleet(self, point_id): return None
    def list_fleet_points(self): return []
    def embed_bm25_document(self, _): return {"indices": [1], "values": [1.0]}
    def embed_bm25_query(self, _): return {"indices": [1], "values": [1.0]}
    def close(self): pass


class Embeddings:
    async def embed_with_context(self, _text, _task): return [0.1, 0.2, 0.3, 0.4]
    async def close(self): pass


class Remote:
    def __init__(self, failures=0): self.failures = failures; self.uploaded = []
    def ensure_collection(self, _dimension): pass
    def upsert_point(self, point):
        if self.failures:
            self.failures -= 1
            raise TimeoutError("offline")
        self.uploaded.append(point)
    def close(self): pass


@pytest.fixture
def setup(tmp_path):
    store = Store()
    db = EdgeStateDB(tmp_path / "state.db")
    outbox, activity = SyncOutbox(db), ActivityLog(db)
    memories = MemoryService(store, Embeddings(), db)
    remote = Remote()
    service = SyncService(store, memories, outbox, db, activity, remote, "robot-1", embedding_dimension=4)
    record = asyncio.run(memories.create(CreateMemory(content="learned maintenance fact", memory_type=MemoryType.LEARNED_FACT)))
    return {"store": store, "db": db, "outbox": outbox, "activity": activity, "memories": memories, "remote": remote, "service": service, "record": record}


def test_upload_marks_revision_uploaded_and_preserves_deterministic_point(setup):
    async def run():
        outbox, activity, memories, remote, service, record = (setup[k] for k in ("outbox", "activity", "memories", "remote", "service", "record"))
        result = await service.run_once()
        assert result.uploaded == 1 and result.failed == 0
        assert [point.id for point in remote.uploaded] == [record.memory_id]
        assert remote.uploaded[0].payload["sync_policy"] == "auto"
        assert remote.uploaded[0].payload["sync_state"] == "UPLOADED"
        assert next(item for item in outbox.all() if item.memory_id == record.memory_id).status == "UPLOADED"
        assert memories.get(record.memory_id).sync_state is SyncState.UPLOADED
        uploaded_item = next(item for item in outbox.all() if item.memory_id == record.memory_id)
        attempts = outbox.attempts(uploaded_item.id)
        assert len(attempts) == 1 and attempts[0]["error"] is None
        assert [e.event_type for e in activity.list(20)].count("SYNC_STARTED") == 1
    asyncio.run(run())


def test_policy_change_during_materialization_cancels_claimed_upload(setup):
    async def run():
        store, db, outbox, remote, service, record = (setup[k] for k in ("store", "db", "outbox", "remote", "service", "record"))
        original_retrieve = store.retrieve
        calls = 0
        def retrieve(memory_id):
            nonlocal calls
            calls += 1
            point = original_retrieve(memory_id)
            if calls == 3:
                with db.transaction() as conn:
                    conn.execute("UPDATE memory_policy SET sensitivity='restricted' WHERE memory_id=?", (memory_id,))
            return point
        store.retrieve = retrieve
        result = await service.run_once()
        item = next(item for item in outbox.all() if item.memory_id == record.memory_id)
        assert result.skipped == 1 and remote.uploaded == []
        assert item.status == "CANCELLED"
        assert setup["memories"].get(record.memory_id).sync_state is SyncState.LOCAL_ONLY
    asyncio.run(run())


def test_materialization_error_records_failed_attempt_and_releases_claim(setup):
    async def run():
        store, outbox, remote, service, record = (setup[k] for k in ("store", "outbox", "remote", "service", "record"))
        original_retrieve = store.retrieve
        calls = 0
        def retrieve(memory_id):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("materialization failed")
            return original_retrieve(memory_id)
        store.retrieve = retrieve
        result = await service.run_once()
        item = next(item for item in outbox.all() if item.memory_id == record.memory_id)
        attempts = outbox.attempts(item.id)
        assert result.failed == 1 and item.status == "RETRY_WAIT"
        assert len(attempts) == 1 and attempts[0]["error"] == "RuntimeError: materialization failed"
        assert remote.uploaded == []
    asyncio.run(run())


def test_remote_failure_records_attempt_and_retries_with_backoff(setup):
    async def run():
        outbox, activity, memories, remote, service, record = (setup[k] for k in ("outbox", "activity", "memories", "remote", "service", "record"))
        remote.failures = 1
        result = await service.run_once()
        assert result.failed == 1
        queued = next(item for item in outbox.all() if item.memory_id == record.memory_id)
        assert queued.status == "RETRY_WAIT" and queued.retry_count == 1
        assert len(outbox.attempts(queued.id)) == 1
        assert memories.get(record.memory_id).sync_state is SyncState.RETRY_WAIT
        assert [e.event_type for e in activity.list(20)].count("SYNC_RETRY") == 1
    asyncio.run(run())


def test_recovered_upload_and_privacy_change_never_send_payload(setup):
    async def run():
        outbox, activity, memories, remote, service, record = (setup[k] for k in ("outbox", "activity", "memories", "remote", "service", "record"))
        item = outbox.pending(10)[0]
        outbox.mark_uploading(item.id)
        service.recover_interrupted()
        with setup["db"].transaction() as conn:
            conn.execute("UPDATE memory_policy SET sensitivity='restricted' WHERE memory_id=?", (record.memory_id,))
        result = await service.run_once()
        assert result.skipped == 1
        assert remote.uploaded == []
        assert next(item for item in outbox.all() if item.memory_id == record.memory_id).status == "CANCELLED"
    asyncio.run(run())


def test_only_one_concurrent_sync_run_uploads(setup):
    async def run():
        remote, service = setup["remote"], setup["service"]
        first, second = await asyncio.gather(service.run_once(), service.run_once())
        assert first.uploaded + second.uploaded == 1
        assert len(remote.uploaded) == 1
    asyncio.run(run())


def test_process_restart_recovers_uploading_item_and_retries_it(setup):
    async def run():
        outbox, remote, service, record = (setup[k] for k in ("outbox", "remote", "service", "record"))
        item = outbox.pending(10)[0]
        outbox.mark_uploading(item.id)
        assert service.recover_interrupted() == 1
        result = await service.run_once()
        assert result.uploaded == 1
        assert [point.id for point in remote.uploaded] == [record.memory_id]
    asyncio.run(run())


def test_worker_discards_queued_noncurrent_revision_before_upload(setup):
    async def run():
        from app.edge.memory.models import ReviseMemory
        outbox, memories, remote, service, record = (setup[k] for k in ("outbox", "memories", "remote", "service", "record"))
        revised = await memories.revise(record.logical_id, ReviseMemory(content="updated learned fact", parent_revision=1))
        result = await service.run_once()
        assert result.uploaded == 1 and result.skipped == 1
        assert [point.id for point in remote.uploaded] == [revised.memory_id]
        states = {item.memory_id: item.status for item in outbox.all()}
        assert states[record.memory_id] == "CANCELLED"
        assert states[revised.memory_id] == "UPLOADED"
    asyncio.run(run())
