import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from app.edge.memory.dedupe import dedupe_hits
from app.edge.memory.hybrid_search import MemoryHit
from app.edge.memory.models import CreateMemory, MemoryType
from app.edge.memory.qdrant_store import QdrantEdgeStore
from app.edge.memory.service import MemoryService
from app.edge.memory.store import MemoryOrigin
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox
from app.edge.sync.service import SyncService


def hit(point_id, origin, revision, content_hash, score, **extra):
    return MemoryHit(point_id, score, origin, score, None, {
        "record_type": "memory", "memory_id": point_id, "logical_id": "pump-procedure",
        "revision": revision, "content_hash": content_hash, **extra,
    })


def test_same_hash_revision_prefers_confirmed_fleet_and_preserves_hit_metadata():
    local = hit("local-v2", MemoryOrigin.LOCAL, 2, "same", 0.8)
    fleet = hit("fleet-v2", MemoryOrigin.FLEET, 2, "same", 0.7,
                sync_timestamp="2026-09-30T10:00:00+00:00")

    result = dedupe_hits([local, fleet])

    assert result == [fleet]
    assert result[0].score == 0.7
    assert result[0].origin is MemoryOrigin.FLEET


def test_unconfirmed_fleet_does_not_replace_local_and_highest_revision_wins():
    old = hit("local-v1", MemoryOrigin.LOCAL, 1, "old", 0.99)
    local = hit("local-v2", MemoryOrigin.LOCAL, 2, "same", 0.4)
    fleet = hit("fleet-v2", MemoryOrigin.FLEET, 2, "same", 0.9)

    assert dedupe_hits([old, fleet, local]) == [local]


def test_same_revision_divergent_hash_is_preserved_for_conflict_handling():
    local = hit("local-v2", MemoryOrigin.LOCAL, 2, "local-content", 0.8)
    fleet = hit("fleet-v2", MemoryOrigin.FLEET, 2, "fleet-content", 0.9,
                sync_timestamp="2026-09-30T10:00:00+00:00")

    assert dedupe_hits([local, fleet]) == [local, fleet]


class Embeddings:
    async def embed_with_context(self, _text, _task):
        return [0.1, 0.2, 0.3, 0.4]


class Remote:
    def health(self):
        return "ONLINE"


def test_cleanup_requires_exact_durable_sync_boundary_and_keeps_fleet_history(tmp_path):
    async def run():
        db = EdgeStateDB(tmp_path / "state.db")
        local_path, fleet_path = tmp_path / "local", tmp_path / "fleet"
        store = QdrantEdgeStore(local_path, fleet_path, embedding_dimension=4)
        store.open()
        memories = MemoryService(store, Embeddings(), db)
        record = await memories.create(CreateMemory(content="pump inspection procedure", memory_type=MemoryType.LEARNED_FACT))
        point = store.retrieve_local(record.memory_id)
        store.close()

        # Seed the immutable fleet shard through the native adapter, then reopen both shards.
        seeder = QdrantEdgeStore(fleet_path, tmp_path / "unused-fleet", embedding_dimension=4)
        seeder.open()
        seeder.upsert_local(point)
        seeder.close()
        store = QdrantEdgeStore(local_path, fleet_path, embedding_dimension=4)
        store.open()
        memories = MemoryService(store, Embeddings(), db)
        outbox, activity = SyncOutbox(db), ActivityLog(db)
        item = next(item for item in outbox.all() if item.memory_id == record.memory_id)
        completion = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
        generation, refresh_id = str(uuid4()), str(uuid4())
        with db.transaction() as conn:
            conn.execute("UPDATE sync_outbox SET status='SYNCHRONIZED',updated_at=? WHERE id=?", (completion.isoformat(), item.id))
            conn.execute("UPDATE memory_policy SET sync_state='SYNCHRONIZED',updated_at=? WHERE memory_id=?", (completion.isoformat(), record.memory_id))
            conn.execute("INSERT INTO sync_checkpoints(checkpoint_id,value,updated_at) VALUES('fleet',?,?)",
                (json.dumps({"generation": generation, "refresh_id": refresh_id, "timestamp": completion.isoformat()}), completion.isoformat()))
            run = {"run_id": "run-1", "status": "SYNCHRONIZED", "updated_at": completion.isoformat(),
                   "fleet_generation": generation, "fleet_refresh_id": refresh_id,
                   "acknowledged": [{"outbox_id": item.id, "memory_id": record.memory_id,
                                     "logical_id": record.logical_id, "revision": record.revision,
                                     "content_hash": record.content_hash}]}
            conn.execute("INSERT INTO sync_checkpoints(checkpoint_id,value,updated_at) VALUES(?,?,?)",
                ("sync-run:run-1", json.dumps(run), completion.isoformat()))
        service = SyncService(store, memories, outbox, db, activity, Remote(), "robot", embedding_dimension=4)

        # A cutoff before the durable completion cannot authorize cleanup.
        assert service.cleanup_confirmed_local(completion.timestamp() - 1) == 0
        assert store.retrieve_local(record.memory_id) is not None
        assert service.cleanup_confirmed_local(completion.timestamp() + 1) == 1
        assert store.retrieve_local(record.memory_id) is None
        assert store.retrieve_fleet(record.memory_id) is not None
        assert memories.get(record.memory_id).content == record.content
        assert memories.history(record.logical_id)[0].memory_id == record.memory_id
        assert service.cleanup_confirmed_local(completion.timestamp() + 1) == 0
        store.close()
        db.close()

    asyncio.run(run())
