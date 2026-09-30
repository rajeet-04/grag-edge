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


def test_upload_claim_and_policy_state_roll_back_atomically(tmp_path: Path):
    db = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(db)
    item = outbox.enqueue("memory-3", "logical-3", 1)
    with db.transaction() as conn:
        conn.execute("INSERT INTO memory_policy(memory_id,logical_id,revision,requested_sync_policy,sensitivity,sync_policy,sync_state,reason_codes_json,is_deleted,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (item.memory_id, item.logical_id, 1, "auto", "normal", "auto", "QUEUED", "[]", 0, "2026-01-01T00:00:00+00:00"))
        conn.execute("CREATE TRIGGER reject_uploading BEFORE UPDATE OF sync_state ON memory_policy WHEN NEW.sync_state='UPLOADING' BEGIN SELECT RAISE(ABORT,'injected policy write failure'); END")
    with pytest.raises(Exception, match="injected policy write failure"):
        outbox.mark_uploading(item.id)
    assert outbox.get(item.id).status == "QUEUED"
    assert outbox.attempts(item.id) == []
    db.close()


def test_attempt_history_distinguishes_failure_then_success(tmp_path: Path):
    db = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(db)
    item = outbox.enqueue("memory-4", "logical-4", 1)
    outbox.mark_uploading(item.id)
    outbox.mark_retry(item.id, "network timeout")
    outbox.mark_uploading(item.id)
    outbox.mark_uploaded(item.id)
    attempts = outbox.attempts(item.id)
    assert [row["result"] for row in attempts] == ["FAILED", "SUCCESS"]
    assert all(row["started_at"] and row["finished_at"] for row in attempts)
    assert attempts[0]["error"] == "network timeout" and attempts[1]["error"] is None
    assert all(row["finished_at"] >= row["started_at"] for row in attempts)
    db.close()


def test_cancel_and_restart_recovery_finalize_attempts(tmp_path: Path):
    db = EdgeStateDB(tmp_path / "state.db")
    outbox = SyncOutbox(db)
    cancelled = outbox.enqueue("memory-5", "logical-5", 1)
    outbox.mark_uploading(cancelled.id)
    outbox.cancel(cancelled.id)
    interrupted = outbox.enqueue("memory-6", "logical-6", 1)
    outbox.mark_uploading(interrupted.id)
    assert outbox.recover_interrupted() == 1
    cancelled_attempt = outbox.attempts(cancelled.id)[0]
    interrupted_attempt = outbox.attempts(interrupted.id)[0]
    assert cancelled_attempt["result"] == "CANCELLED" and cancelled_attempt["finished_at"]
    assert interrupted_attempt["result"] == "INTERRUPTED" and interrupted_attempt["finished_at"]
    assert outbox.get(interrupted.id).status == "QUEUED"
    db.close()


def test_legacy_attempt_table_migrates_without_losing_history(tmp_path: Path):
    import sqlite3

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sync_attempts(id TEXT PRIMARY KEY,outbox_id TEXT NOT NULL,attempt_number INTEGER NOT NULL,error TEXT,created_at TEXT NOT NULL,UNIQUE(outbox_id,attempt_number))")
    conn.execute("INSERT INTO sync_attempts VALUES('attempt-1','outbox-1',1,'network timeout','2026-09-30T00:00:00+00:00')")
    conn.commit()
    conn.close()

    db = EdgeStateDB(path)
    columns = {row["name"] for row in db._connection.execute("PRAGMA table_info(sync_attempts)")}
    row = db._connection.execute("SELECT * FROM sync_attempts WHERE id='attempt-1'").fetchone()
    assert {"started_at", "finished_at", "result"} <= columns
    assert row["started_at"] == "2026-09-30T00:00:00+00:00"
    assert row["finished_at"] == row["started_at"] and row["result"] == "FAILED"
    db.close()
