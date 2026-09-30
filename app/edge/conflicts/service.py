"""Detect and durably record conflict-sensitive memory divergence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.edge.memory.models import MemoryRecord, MemoryType, SyncState, utcnow
from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB


_CONFLICT_SENSITIVE = frozenset({MemoryType.PROCEDURE, MemoryType.LEARNED_FACT})


class ConflictRecord(BaseModel):
    """Control-plane metadata describing two retained memory revisions.

    Content itself is intentionally excluded: SQLite stores references, hashes,
    and provenance, while the immutable/local memory stores remain authoritative.
    """

    model_config = ConfigDict(frozen=True)

    conflict_id: str
    logical_id: str
    local_memory_id: str
    fleet_memory_id: str
    base_revision: int | None
    memory_type: MemoryType
    local_revision: int
    fleet_revision: int
    local_content_hash: str
    fleet_content_hash: str
    local_device_id: str | None
    fleet_device_id: str | None
    local_source_type: str | None
    local_source_id: str | None
    fleet_source_type: str | None
    fleet_source_id: str | None
    local_created_at: datetime
    local_updated_at: datetime
    fleet_created_at: datetime
    fleet_updated_at: datetime
    local_sync_state: SyncState
    fleet_sync_state: SyncState
    detected_at: datetime
    status: str = "OPEN"


class ConflictService:
    """Persist and query open conflicts using the existing SQLite table."""

    def __init__(self, db: EdgeStateDB, activity: ActivityLog | None = None) -> None:
        self.db = db
        self.activity = activity or ActivityLog(db)

    @staticmethod
    def _identity(local: MemoryRecord, fleet: MemoryRecord) -> dict[str, object]:
        return {
            "logical_id": local.logical_id,
            "base_revision": local.parent_revision,
            "memory_type": local.memory_type.value,
            "local_memory_id": local.memory_id,
            "fleet_memory_id": fleet.memory_id,
            "local_content_hash": local.content_hash,
            "fleet_content_hash": fleet.content_hash,
        }

    @classmethod
    def _new_conflict(cls, local: MemoryRecord, fleet: MemoryRecord) -> ConflictRecord:
        identity = cls._identity(local, fleet)
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ConflictRecord(
            conflict_id=f"conflict_{digest}",
            logical_id=local.logical_id,
            local_memory_id=local.memory_id,
            fleet_memory_id=fleet.memory_id,
            base_revision=local.parent_revision,
            memory_type=local.memory_type,
            local_revision=local.revision,
            fleet_revision=fleet.revision,
            local_content_hash=local.content_hash,
            fleet_content_hash=fleet.content_hash,
            local_device_id=local.device_id,
            fleet_device_id=fleet.device_id,
            local_source_type=local.source_type,
            local_source_id=local.source_id,
            fleet_source_type=fleet.source_type,
            fleet_source_id=fleet.source_id,
            local_created_at=local.created_at,
            local_updated_at=local.updated_at,
            fleet_created_at=fleet.created_at,
            fleet_updated_at=fleet.updated_at,
            local_sync_state=local.sync_state,
            fleet_sync_state=fleet.sync_state,
            detected_at=utcnow(),
        )

    @staticmethod
    def _record_from_row(row) -> ConflictRecord | None:
        """Decode rows written by this service; ignore pre-existing legacy rows."""
        try:
            return ConflictRecord.model_validate_json(row["metadata_json"])
        except (TypeError, ValueError):
            return None

    def detect(self, local: MemoryRecord, fleet: MemoryRecord) -> ConflictRecord | None:
        """Record divergent sensitive revisions which share an immediate base."""
        if local.logical_id != fleet.logical_id or local.memory_type is not fleet.memory_type:
            return None
        if local.memory_type not in _CONFLICT_SENSITIVE:
            return None
        if local.parent_revision != fleet.parent_revision:
            return None
        if local.parent_revision is None and local.revision != fleet.revision:
            return None
        if local.content == fleet.content:
            return None

        candidate = self._new_conflict(local, fleet)
        # BEGIN IMMEDIATE serializes competing detector calls. Conflict and event
        # are committed atomically; only the transaction which creates the row
        # appends the event.
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM conflicts WHERE conflict_id=?", (candidate.conflict_id,)).fetchone()
            if row is not None:
                return self._record_from_row(row)
            payload = candidate.model_dump_json()
            cursor = conn.execute(
                "INSERT INTO conflicts(conflict_id,logical_id,local_memory_id,fleet_memory_id,status,created_at,metadata_json) "
                "VALUES(?,?,?,?,?,?,?)",
                (candidate.conflict_id, candidate.logical_id, candidate.local_memory_id, candidate.fleet_memory_id,
                 candidate.status, candidate.detected_at.isoformat(), payload),
            )
            if cursor.rowcount:
                self.activity.append_in_transaction(conn, ActivityEvent(
                    event_id=f"{candidate.conflict_id}:detected",
                    event_type="CONFLICT_DETECTED",
                    device_id=local.device_id or "edge",
                    memory_id=local.memory_id,
                    timestamp=candidate.detected_at,
                    severity="warning",
                    message="Divergent memory revisions detected",
                    metadata={
                        "conflict_id": candidate.conflict_id,
                        "logical_id": candidate.logical_id,
                        "base_revision": candidate.base_revision,
                        "local_memory_id": candidate.local_memory_id,
                        "fleet_memory_id": candidate.fleet_memory_id,
                    },
                ))
        return candidate

    def list_open(self) -> list[ConflictRecord]:
        with self.db._lock:
            rows = self.db._connection.execute(
                "SELECT * FROM conflicts WHERE status='OPEN' ORDER BY created_at, conflict_id"
            ).fetchall()
        return [record for row in rows if (record := self._record_from_row(row)) is not None]

    def get(self, conflict_id: str) -> ConflictRecord | None:
        with self.db._lock:
            row = self.db._connection.execute(
                "SELECT * FROM conflicts WHERE conflict_id=?", (conflict_id,)
            ).fetchone()
        return self._record_from_row(row) if row is not None else None
