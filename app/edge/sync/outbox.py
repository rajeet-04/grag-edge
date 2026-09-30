"""Durable idempotent synchronization outbox."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.edge.state.sqlite import EdgeStateDB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class OutboxItem:
    id: str
    memory_id: str
    logical_id: str
    revision: int
    status: str
    retry_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class SyncOutbox:
    def __init__(self, db: EdgeStateDB):
        self.db = db

    @staticmethod
    def _item(row: sqlite3.Row) -> OutboxItem:
        return OutboxItem(
            id=row["id"], memory_id=row["memory_id"], logical_id=row["logical_id"],
            revision=row["revision"], status=row["status"], retry_count=row["retry_count"],
            last_error=row["last_error"], created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _select(conn: sqlite3.Connection, outbox_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM sync_outbox WHERE id = ?", (outbox_id,)).fetchone()
        if row is None:
            raise KeyError(outbox_id)
        return row

    def enqueue(self, memory_id: str, logical_id: str, revision: int) -> OutboxItem:
        now, candidate_id = _now(), str(uuid4())
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM sync_outbox WHERE logical_id = ? AND revision = ?",
                (logical_id, revision),
            ).fetchone()
            if row is not None:
                if row["memory_id"] != memory_id:
                    raise ValueError("outbox identity collision for logical_id/revision")
                return self._item(row)
            row = conn.execute("SELECT * FROM sync_outbox WHERE memory_id = ?", (memory_id,)).fetchone()
            if row is not None:
                if row["logical_id"] != logical_id or row["revision"] != revision:
                    raise ValueError("outbox identity collision for memory_id")
                return self._item(row)
            conn.execute(
                "INSERT INTO sync_outbox(id,memory_id,logical_id,revision,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (candidate_id, memory_id, logical_id, revision, "QUEUED", now, now),
            )
            return self._item(self._select(conn, candidate_id))

    def pending(self, limit: int) -> list[OutboxItem]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.db._lock:
            rows = self.db._connection.execute(
                "SELECT * FROM sync_outbox WHERE status IN ('QUEUED','RETRY_WAIT') "
                "ORDER BY created_at, id LIMIT ?", (limit,),
            ).fetchall()
        return [self._item(row) for row in rows]

    def get(self, outbox_id: str) -> OutboxItem:
        with self.db._lock:
            return self._item(self._select(self.db._connection, outbox_id))

    def all(self) -> list[OutboxItem]:
        with self.db._lock:
            rows = self.db._connection.execute("SELECT * FROM sync_outbox ORDER BY created_at, id").fetchall()
        return [self._item(row) for row in rows]

    def attempts(self, outbox_id: str) -> list[sqlite3.Row]:
        with self.db._lock:
            return list(self.db._connection.execute(
                "SELECT * FROM sync_attempts WHERE outbox_id = ? ORDER BY attempt_number", (outbox_id,)
            ).fetchall())

    def mark_uploading(self, outbox_id: str) -> OutboxItem:
        with self.db.transaction() as conn:
            row = self._select(conn, outbox_id)
            if row["status"] in ("QUEUED", "RETRY_WAIT"):
                conn.execute("UPDATE sync_outbox SET status='UPLOADING', updated_at=? WHERE id=?", (_now(), outbox_id))
            elif row["status"] != "UPLOADING":
                raise ValueError(f"cannot start upload from {row['status']}")
            return self._item(self._select(conn, outbox_id))

    def mark_retry(self, outbox_id: str, error: str) -> OutboxItem:
        now = _now()
        with self.db.transaction() as conn:
            row = self._select(conn, outbox_id)
            if row["status"] != "UPLOADING":
                raise ValueError(f"cannot mark retry from {row['status']}")
            attempt = row["retry_count"] + 1
            conn.execute(
                "UPDATE sync_outbox SET status='RETRY_WAIT', retry_count=?, last_error=?, updated_at=? WHERE id=?",
                (attempt, error, now, outbox_id),
            )
            conn.execute(
                "INSERT INTO sync_attempts(id,outbox_id,attempt_number,error,created_at) VALUES(?,?,?,?,?)",
                (str(uuid4()), outbox_id, attempt, error, now),
            )
            return self._item(self._select(conn, outbox_id))

    def mark_uploaded(self, outbox_id: str) -> OutboxItem:
        with self.db.transaction() as conn:
            row = self._select(conn, outbox_id)
            if row["status"] == "UPLOADED":
                return self._item(row)
            if row["status"] != "UPLOADING":
                raise ValueError(f"cannot mark uploaded from {row['status']}")
            conn.execute("UPDATE sync_outbox SET status='UPLOADED', updated_at=? WHERE id=?", (_now(), outbox_id))
            return self._item(self._select(conn, outbox_id))
