"""Append-only activity event persistence."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.edge.state.sqlite import EdgeStateDB


class ActivityEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    device_id: str
    memory_id: str | None = None
    timestamp: datetime
    severity: str = "info"
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityLog:
    def __init__(self, db: EdgeStateDB):
        self.db = db

    def append(self, event: ActivityEvent) -> None:
        with self.db.transaction() as conn:
            self.append_in_transaction(conn, event)

    @staticmethod
    def append_in_transaction(conn, event: ActivityEvent) -> None:
        row = conn.execute("SELECT * FROM activity_events WHERE event_id=?", (event.event_id,)).fetchone()
        values = (
            event.event_type, event.device_id, event.memory_id, event.timestamp.isoformat(),
            event.severity, event.message, json.dumps(event.metadata, sort_keys=True),
        )
        if row is not None:
            existing = tuple(row[name] for name in (
                "event_type", "device_id", "memory_id", "timestamp", "severity", "message", "metadata_json"
            ))
            if existing != values:
                raise ValueError("activity event identity collision")
            return
        conn.execute(
            "INSERT INTO activity_events(event_id,event_type,device_id,memory_id,timestamp,severity,message,metadata_json) "
            "VALUES(?,?,?,?,?,?,?,?)", (event.event_id, *values),
        )

    @staticmethod
    def _event(row) -> ActivityEvent:
        return ActivityEvent(
            event_id=row["event_id"], event_type=row["event_type"], device_id=row["device_id"],
            memory_id=row["memory_id"], timestamp=datetime.fromisoformat(row["timestamp"]),
            severity=row["severity"], message=row["message"], metadata=json.loads(row["metadata_json"]),
        )

    def list(self, limit: int, before: datetime | None = None) -> list[ActivityEvent]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.db._lock:
            if before is None:
                rows = self.db._connection.execute(
                    "SELECT * FROM activity_events ORDER BY sequence DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self.db._connection.execute(
                    "SELECT * FROM activity_events WHERE timestamp < ? ORDER BY sequence DESC LIMIT ?",
                    (before.isoformat(), limit),
                ).fetchall()
        return [self._event(row) for row in rows]

    def latest_id(self) -> str | None:
        with self.db._lock:
            row = self.db._connection.execute(
                "SELECT event_id FROM activity_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        return row["event_id"] if row else None
