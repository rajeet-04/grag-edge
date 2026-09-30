"""Atomic policy decision, outbox, and activity transitions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.edge.memory.models import MemoryRecord, Sensitivity, SyncPolicy, SyncState
from app.edge.policy.engine import SyncDecision
from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import SyncOutbox


class PolicyWorkflow:
    """Coordinates SQLite metadata and its exact outbox/activity side effects."""

    def __init__(self, db: EdgeStateDB):
        self.db = db
        self.outbox = SyncOutbox(db)
        self.activity = ActivityLog(db)

    @staticmethod
    def _view(row: Any) -> dict[str, Any]:
        if row is None:
            return None
        return {
            "memory_id": row["memory_id"], "logical_id": row["logical_id"],
            "revision": row["revision"], "requested_sync_policy": row["requested_sync_policy"],
            "sync_policy": row["sync_policy"], "sync_state": row["sync_state"],
            "sync_reason_codes": tuple(json.loads(row["reason_codes_json"])),
            "sensitivity": row["sensitivity"], "is_deleted": bool(row["is_deleted"]),
        }

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self.db._lock:
            row = self.db._connection.execute(
                "SELECT * FROM memory_policy WHERE memory_id=?", (memory_id,)
            ).fetchone()
        return self._view(row)

    def commit_record(
        self,
        record: MemoryRecord,
        decision: SyncDecision,
        state: SyncState,
        memory_event: str,
    ) -> dict[str, Any]:
        with self.db.transaction() as conn:
            existing = conn.execute("SELECT * FROM memory_policy WHERE memory_id=?", (record.memory_id,)).fetchone()
            if existing is not None:
                if existing["logical_id"] != record.logical_id or existing["revision"] != record.revision:
                    raise ValueError("memory policy identity collision")
                if state is SyncState.QUEUED:
                    SyncOutbox.enqueue_in_transaction(conn, record.memory_id, record.logical_id, record.revision)
                return self._view(existing)

            latest = conn.execute(
                "SELECT * FROM memory_policy WHERE logical_id=? ORDER BY revision DESC LIMIT 1",
                (record.logical_id,),
            ).fetchone()
            if record.revision == 1 and latest is not None:
                raise ValueError("logical_id already has a persisted root revision")
            if record.revision > 1 and latest is not None and latest["revision"] != record.parent_revision:
                raise ValueError("stale persisted parent revision")
            if record.revision > 1 and latest is None and record.parent_revision != record.revision - 1:
                raise ValueError("invalid revision parent")

            requested = record.requested_sync_policy.value if record.requested_sync_policy else None
            effective = decision.action.value
            reason_codes = tuple(decision.reason_codes)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO memory_policy(memory_id,logical_id,revision,requested_sync_policy,sync_policy,sync_state,"
                "reason_codes_json,sensitivity,is_deleted,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (record.memory_id, record.logical_id, record.revision, requested, effective, state.value,
                 json.dumps(reason_codes), record.sensitivity.value, int(record.is_deleted), now),
            )
            if state is SyncState.QUEUED:
                if record.is_deleted or record.sensitivity is Sensitivity.RESTRICTED or decision.action is not SyncPolicy.AUTO:
                    raise ValueError("privacy policy forbids enqueueing this record")
                SyncOutbox.enqueue_in_transaction(conn, record.memory_id, record.logical_id, record.revision)
            self._event(conn, record, memory_event, "Memory record stored", {"revision": record.revision})
            if state is SyncState.LOCAL_ONLY:
                self._event(conn, record, "POLICY_LOCAL_ONLY", "Memory remains local", {"reason_codes": reason_codes})
            elif state is SyncState.QUEUED:
                self._event(conn, record, "SYNC_QUEUED", "Memory queued for synchronization", {"reason_codes": reason_codes})
            return self._view(conn.execute("SELECT * FROM memory_policy WHERE memory_id=?", (record.memory_id,)).fetchone())

    def transition_approval(self, record: MemoryRecord, approve: bool) -> dict[str, Any]:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM memory_policy WHERE memory_id=?", (record.memory_id,)).fetchone()
            if row is None:
                raise KeyError(record.memory_id)
            latest = conn.execute(
                "SELECT * FROM memory_policy WHERE logical_id=? ORDER BY revision DESC LIMIT 1",
                (record.logical_id,),
            ).fetchone()
            if latest is None or latest["memory_id"] != record.memory_id or latest["revision"] != record.revision:
                raise ValueError("approval target is not the current revision")
            if row["is_deleted"] or record.is_deleted:
                raise ValueError("deleted memories cannot be approved or rejected")
            if row["sensitivity"] == Sensitivity.RESTRICTED.value:
                raise ValueError("restricted memories cannot be synchronized")

            if approve:
                if row["sync_state"] == SyncState.QUEUED.value and row["sync_policy"] == SyncPolicy.AUTO.value:
                    return self._view(row)
                if row["sync_state"] != SyncState.AWAITING_APPROVAL.value:
                    raise ValueError("memory is not awaiting approval")
                reasons = tuple(json.loads(row["reason_codes_json"])) + ("operator_approved",)
                now = datetime.now(timezone.utc).isoformat()
                SyncOutbox.enqueue_in_transaction(conn, record.memory_id, record.logical_id, record.revision)
                conn.execute(
                    "UPDATE memory_policy SET sync_policy=?,sync_state=?,reason_codes_json=?,updated_at=? WHERE memory_id=?",
                    (SyncPolicy.AUTO.value, SyncState.QUEUED.value, json.dumps(reasons), now, record.memory_id),
                )
                self._event(conn, record, "POLICY_SYNC_APPROVED", "Operator approved synchronization", {"revision": record.revision})
                self._event(conn, record, "SYNC_QUEUED", "Memory queued for synchronization", {"reason_codes": reasons})
            else:
                if row["sync_state"] == SyncState.LOCAL_ONLY.value and row["sync_policy"] == SyncPolicy.LOCAL_ONLY.value:
                    return self._view(row)
                if row["sync_state"] not in (SyncState.AWAITING_APPROVAL.value, SyncState.QUEUED.value, SyncState.RETRY_WAIT.value):
                    raise ValueError(f"cannot reject memory from state {row['sync_state']}")
                outbox = conn.execute(
                    "SELECT * FROM sync_outbox WHERE memory_id=?", (record.memory_id,)
                ).fetchone()
                if outbox is not None:
                    if outbox["status"] == "UPLOADING":
                        raise ValueError("cannot reject a memory while upload is in progress")
                    if outbox["status"] in ("QUEUED", "RETRY_WAIT"):
                        conn.execute(
                            "UPDATE sync_outbox SET status='CANCELLED',updated_at=? WHERE id=?",
                            (datetime.now(timezone.utc).isoformat(), outbox["id"]),
                        )
                reasons = tuple(json.loads(row["reason_codes_json"])) + ("operator_rejected",)
                conn.execute(
                    "UPDATE memory_policy SET sync_policy=?,sync_state=?,reason_codes_json=?,updated_at=? WHERE memory_id=?",
                    (SyncPolicy.LOCAL_ONLY.value, SyncState.LOCAL_ONLY.value, json.dumps(reasons),
                     datetime.now(timezone.utc).isoformat(), record.memory_id),
                )
                self._event(conn, record, "POLICY_LOCAL_ONLY", "Operator rejected synchronization", {"reason_codes": reasons})
            return self._view(conn.execute("SELECT * FROM memory_policy WHERE memory_id=?", (record.memory_id,)).fetchone())

    @staticmethod
    def _event(conn, record: MemoryRecord, event_type: str, message: str, metadata: dict[str, Any]) -> None:
        event = ActivityEvent(
            event_id=str(uuid4()), event_type=event_type, device_id=record.device_id or "unknown",
            memory_id=record.memory_id, timestamp=datetime.now(timezone.utc), severity="info",
            message=message, metadata={"logical_id": record.logical_id, **metadata},
        )
        ActivityLog.append_in_transaction(conn, event)
