from pathlib import Path

import pytest

from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox


def test_outbox_survives_restart_and_duplicate_enqueue_is_idempotent(tmp_path: Path):
    db = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(db)
    original = outbox.enqueue("memory-1", "logical-1", 1)
    db.close()

    reopened = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(reopened)
    duplicate = outbox.enqueue("memory-1", "logical-1", 1)
    assert duplicate.id == original.id
    assert [(item.memory_id, item.status) for item in outbox.pending(10)] == [("memory-1", "QUEUED")]
    reopened.close()


def test_outbox_identity_collision_fails_even_for_terminal_items(tmp_path: Path):
    db = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(db)
    item = outbox.enqueue("memory-1", "logical-1", 1)
    outbox.mark_uploading(item.id)
    outbox.mark_uploaded(item.id)
    assert outbox.enqueue("memory-1", "logical-1", 1).id == item.id
    with pytest.raises(ValueError, match="identity collision"):
        outbox.enqueue("different-memory", "logical-1", 1)
    db.close()


def test_retry_count_and_pending_work_survive_restart(tmp_path: Path):
    db = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(db)
    item = outbox.enqueue("memory-2", "logical-2", 3)
    outbox.mark_uploading(item.id)
    outbox.mark_retry(item.id, "offline")
    db.close()

    reopened = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(reopened)
    pending = outbox.pending(10)
    assert len(pending) == 1
    assert pending[0].retry_count == 1 and pending[0].status == "RETRY_WAIT"
    assert len(outbox.attempts(item.id)) == 1
    reopened.close()
