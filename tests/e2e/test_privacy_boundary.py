"""RESTRICTED / LOCAL_ONLY memories must never reach a remote upload payload."""
import pytest

from app.edge.memory.hybrid_search import SearchMode

from app.edge.memory.models import CreateMemory, ReviseMemory, Sensitivity
from tests.e2e._edge_harness import CapturingCloud, open_runtime


def _create(edge, **kw):
    return edge.memories.create(CreateMemory(**kw))


@pytest.mark.parametrize("kwargs", [
    {"sync_policy": "local_only"},
    {"sensitivity": "restricted", "sync_policy": "auto", "importance": "critical", "memory_type": "incident", "confidence": 0.99},
    {"sensitivity": "restricted", "sync_policy": "approval_required"},
])
async def test_blocked_memory_has_zero_remote_upload_attempts(tmp_path, kwargs):
    cloud = CapturingCloud()
    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    record = await _create(edge, content="site-secret torque values", **kwargs)
    # Even an explicit operator approval cannot override privacy.
    try:
        await edge.memories.approve(record.memory_id)
    except (ValueError, KeyError):
        pass
    for _ in range(3):
        await edge.sync.run_once()
    assert [c for c in cloud.calls if c[0] == "upsert_point"] == []
    assert cloud.uploaded == []
    # Content is still locally searchable.
    hits = await edge.search.search("site-secret torque values", SearchMode.HYBRID, 5)
    assert record.memory_id in [h.point_id for h in hits]
    await edge.close()


async def test_uploaded_payload_carries_no_restricted_or_local_only_neighbour(tmp_path):
    cloud = CapturingCloud()
    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    shared = await _create(edge, content="shareable learned fact", sync_policy="auto", memory_type="learned_fact", importance="high", confidence=0.95)
    private = await _create(edge, content="restricted note", sensitivity="restricted", sync_policy="auto")
    local = await _create(edge, content="local only note", sync_policy="local_only")
    await edge.sync.run_once()
    ids = {p.id for p in cloud.uploaded}
    assert private.memory_id not in ids and local.memory_id not in ids
    for point in cloud.uploaded:
        text = str(point.payload)
        assert "restricted note" not in text and "local only note" not in text
    await edge.close()


async def test_privacy_downgrade_after_queue_blocks_upload(tmp_path):
    cloud = CapturingCloud()
    edge = open_runtime(tmp_path, cloud)
    await edge.start()
    record = await _create(edge, content="fact later marked private", sync_policy="auto", memory_type="learned_fact", importance="high", confidence=0.95)
    await edge.memories.revise(record.logical_id, ReviseMemory(content=record.content, parent_revision=record.revision, sensitivity=Sensitivity.RESTRICTED))
    await edge.sync.run_once()
    assert cloud.uploaded == []
    await edge.close()
