"""Detect and durably record conflict-sensitive memory divergence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict

from app.edge.memory.models import MemoryRecord, MemoryType, SyncState, utcnow
from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB


_CONFLICT_SENSITIVE = frozenset({MemoryType.PROCEDURE, MemoryType.LEARNED_FACT})
_OPEN_STATUSES = ("OPEN", "RESOLVING")
RESOLUTIONS = frozenset({"KEEP_LOCAL", "ACCEPT_FLEET", "MERGE"})


class ConflictResolutionError(ValueError):
    """Raised when a resolution request is invalid or contradicts a prior one."""


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
    resolution: str | None = None
    resolution_memory_id: str | None = None
    resolution_revision: int | None = None
    resolved_at: datetime | None = None


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
            record = ConflictRecord.model_validate_json(row["metadata_json"])
        except (TypeError, ValueError):
            return None
        return record.model_copy(update={"status": row["status"]})

    def _covered_by_resolution(self, local: MemoryRecord, fleet: MemoryRecord) -> bool:
        """True when a recorded resolution of this fleet branch precedes the local revision."""
        with self.db._lock:
            rows = self.db._connection.execute(
                "SELECT metadata_json FROM conflicts WHERE logical_id=? AND fleet_memory_id=? AND status='RESOLVED'",
                (local.logical_id, fleet.memory_id),
            ).fetchall()
        for row in rows:
            try:
                resolved = ConflictRecord.model_validate_json(row["metadata_json"])
            except ValueError:
                continue
            if resolved.resolution_revision is not None and local.revision >= resolved.resolution_revision:
                return True
        return False

    def detect(
        self,
        local: MemoryRecord,
        fleet: MemoryRecord,
        local_history: Iterable[MemoryRecord] | None = None,
        fleet_history: Iterable[MemoryRecord] | None = None,
    ) -> ConflictRecord | None:
        """Record divergent sensitive revisions of one logical memory.

        Without lineage evidence only branches sharing an immediate base compare.
        With histories, a branch is never a conflict with its own ancestor, and
        differing parents are conflicts only when neither side descends from the
        other; revision numbers alone never decide a winner.
        """
        if local.logical_id != fleet.logical_id or local.memory_type is not fleet.memory_type:
            return None
        if local.memory_type not in _CONFLICT_SENSITIVE or local.is_deleted or fleet.is_deleted:
            return None
        if local.content == fleet.content or local.memory_id == fleet.memory_id:
            return None
        if local_history is not None and fleet_history is not None:
            if local.memory_id in {r.memory_id for r in fleet_history} or fleet.memory_id in {r.memory_id for r in local_history}:
                return None
        elif local.parent_revision != fleet.parent_revision:
            return None
        if local.parent_revision == fleet.parent_revision and local.parent_revision is None and local.revision != fleet.revision:
            return None
        if self._covered_by_resolution(local, fleet):
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
                "SELECT * FROM conflicts WHERE status IN ('OPEN','RESOLVING') ORDER BY created_at, conflict_id"
            ).fetchall()
        return [record for row in rows if (record := self._record_from_row(row)) is not None]

    def get(self, conflict_id: str) -> ConflictRecord | None:
        with self.db._lock:
            row = self.db._connection.execute(
                "SELECT * FROM conflicts WHERE conflict_id=?", (conflict_id,)
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def open_count(self) -> int:
        with self.db._lock:
            return self.db._connection.execute(
                "SELECT COUNT(*) FROM conflicts WHERE status IN ('OPEN','RESOLVING')"
            ).fetchone()[0]

    def open_logical_ids(self) -> set[str]:
        return {conflict.logical_id for conflict in self.list_open()}

    async def resolve(self, conflict_id: str, resolution: str, memories: Any, merged_content: str | None = None) -> ConflictRecord:
        """Resolve by writing one new local revision above both branches.

        The claim, deterministic new memory id and single-winner finalization make
        concurrent, repeated and post-crash requests converge on one revision and
        one CONFLICT_RESOLVED event. Both branches remain in history.
        """
        if resolution not in RESOLUTIONS:
            raise ConflictResolutionError("unknown resolution")
        if resolution == "MERGE" and not (merged_content and merged_content.strip()):
            raise ConflictResolutionError("MERGE requires merged content")
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM conflicts WHERE conflict_id=?", (conflict_id,)).fetchone()
            if row is None:
                raise KeyError(conflict_id)
            conflict = self._record_from_row(row)
            if conflict is None:
                raise KeyError(conflict_id)
            if conflict.status != "OPEN" and conflict.resolution != resolution:
                raise ConflictResolutionError("conflict already resolved with " + str(conflict.resolution))
            if conflict.status == "OPEN":
                claimed = conflict.model_copy(update={
                    "status": "RESOLVING", "resolution": resolution,
                    "resolution_memory_id": str(uuid5(NAMESPACE_URL, "grag-resolution:" + conflict_id)),
                    "resolution_revision": max(conflict.local_revision, conflict.fleet_revision) + 1,
                })
                conn.execute("UPDATE conflicts SET status='RESOLVING',metadata_json=? WHERE conflict_id=?",
                             (claimed.model_dump_json(), conflict_id))
                conflict = claimed
        if conflict.status == "RESOLVED":
            return conflict
        if resolution == "KEEP_LOCAL":
            source = memories.get(conflict.local_memory_id)
        elif resolution == "ACCEPT_FLEET":
            source = memories.get(conflict.fleet_memory_id)
        else:
            source = None
        content = merged_content if resolution == "MERGE" else (source.content if source else None)
        if content is None:
            raise ConflictResolutionError("resolution source memory is unavailable")
        await memories.write_resolution(conflict, content)
        now = utcnow()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM conflicts WHERE conflict_id=?", (conflict_id,)).fetchone()
            current = self._record_from_row(row)
            if current.status == "RESOLVED":
                return current
            done = current.model_copy(update={"status": "RESOLVED", "resolved_at": now})
            conn.execute("UPDATE conflicts SET status='RESOLVED',metadata_json=? WHERE conflict_id=?",
                         (done.model_dump_json(), conflict_id))
            self.activity.append_in_transaction(conn, ActivityEvent(
                event_id=f"{conflict_id}:resolved", event_type="CONFLICT_RESOLVED",
                device_id=done.local_device_id or "edge", memory_id=done.resolution_memory_id, timestamp=now,
                message="Memory conflict resolved",
                metadata={"conflict_id": conflict_id, "logical_id": done.logical_id, "resolution": done.resolution,
                          "resolution_memory_id": done.resolution_memory_id, "resolution_revision": done.resolution_revision}))
            return done
