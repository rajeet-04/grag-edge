"""Restart at each sync boundary preserves queue, checkpoint, and conflict state."""
from datetime import datetime, timezone
from hashlib import sha256

from app.edge.memory.models import CreateMemory, MemoryRecord, MemoryType, SyncState
from app.edge.sync.server_client import CloudHealth
from tests.e2e._edge_harness import CapturingCloud, open_runtime

FACT = dict(content="pump seal replaced", sync_policy="auto", memory_type="learned_fact", importance="high", confidence=0.95)


def statuses(edge):
    return [item.status for item in edge.outbox.all()]


async def test_offline_restart_keeps_queue_and_uploads_once_when_online(tmp_path):
    offline = CapturingCloud(CloudHealth.OFFLINE)
    edge = open_runtime(tmp_path, offline)
    await edge.start()
    record = await edge.memories.create(CreateMemory(**FACT))
    await edge.sync.run_once()
    assert offline.uploaded == [] and statuses(edge) == ["QUEUED"]
    await edge.close()

    online = CapturingCloud()
    edge = open_runtime(tmp_path, online)
    await edge.start()
    assert edge.memories.get(record.memory_id) is not None
    assert statuses(edge) == ["QUEUED"]
    await edge.sync.run_once()
    await edge.sync.run_once()
    assert [p.id for p in online.uploaded] == [record.memory_id]
    await edge.close()


async def test_queued_upload_restart_recovers_interrupted_uploading(tmp_path):
    cloud = CapturingCloud()
    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    record = await edge.memories.create(CreateMemory(**FACT))
    item = edge.outbox.all()[0]
    edge.outbox.mark_uploading(item.id)  # crash mid-upload
    await edge.close()

    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    assert statuses(edge)[0] in ("QUEUED", "RETRY_WAIT", "UPLOADING")
    for _ in range(3):
        await edge.sync.run_once()
    assert record.memory_id in {p.id for p in cloud.uploaded}
    assert statuses(edge) == ["UPLOADED"]
    await edge.close()


async def test_restart_after_upload_before_fleet_refresh_does_not_reupload_or_lose_state(tmp_path):
    cloud = CapturingCloud()
    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    record = await edge.memories.create(CreateMemory(**FACT))
    await edge.sync.run_once()
    assert statuses(edge) == ["UPLOADED"] and len(cloud.uploaded) == 1
    await edge.close()

    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    assert statuses(edge) == ["UPLOADED"]  # not synchronized without a confirmed fleet refresh
    assert edge.memories.get(record.memory_id).sync_state is not SyncState.SYNCHRONIZED
    await edge.sync.run_once()
    assert len(cloud.uploaded) == 1
    await edge.close()


async def test_unresolved_conflict_survives_restart(tmp_path):
    cloud = CapturingCloud()
    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)

    def rec(mid, content, device):
        return MemoryRecord(memory_id=mid, logical_id="pump-procedure", device_id=device, memory_type=MemoryType.PROCEDURE,
            content=content, created_at=now, updated_at=now, revision=2, parent_revision=1,
            content_hash=sha256(content.encode()).hexdigest(), source_type="operator", source_id="s", sync_state=SyncState.LOCAL_DIRTY)

    created = edge.conflicts.detect(rec("local-v2", "Inspect seal first", "r1"), rec("fleet-v2", "Check bearing first", "r2"))
    assert edge.conflicts.open_count() == 1
    await edge.close()

    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    assert edge.conflicts.open_count() == 1
    assert edge.conflicts.get(created.conflict_id).status == "OPEN"
    await edge.sync.run_once()
    assert edge.conflicts.open_count() == 1
    await edge.close()
