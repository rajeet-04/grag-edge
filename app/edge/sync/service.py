"""Idempotent worker that uploads only the current eligible edge revision."""
from __future__ import annotations

import asyncio
import json
from uuid import NAMESPACE_URL, uuid5
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

from app.edge.memory.models import MemoryRecord, Sensitivity, SyncPolicy, SyncState
from app.edge.memory.store import StoredPoint
from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.outbox import OutboxItem, SyncOutbox
from app.edge.sync.server_client import CloudHealth


@dataclass(frozen=True, slots=True)
class SyncRunResult:
    status: str
    uploaded: int = 0
    failed: int = 0
    skipped: int = 0
    pending: int = 0
    synchronized: int = 0
    snapshot_pending: int = 0
    refresh_error: str | None = None


class SyncService:
    def __init__(self, store: Any, memories: Any, outbox: SyncOutbox, db: EdgeStateDB, activity: ActivityLog, remote: Any, device_id: str, embedding_dimension: int = 768, batch_size: int = 50, snapshots: Any | None = None, conflicts: Any | None = None):
        self.store, self.memories, self.outbox = store, memories, outbox
        self.db, self.activity, self.remote = db, activity, remote
        self.device_id, self.embedding_dimension, self.batch_size = device_id, embedding_dimension, batch_size
        self.snapshots = snapshots
        self.conflicts = conflicts
        self._run_lock = asyncio.Lock()

    @staticmethod
    async def _blocking(function, *args):
        job = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(job)
        except asyncio.CancelledError:
            await job
            raise

    def recover_interrupted(self) -> int:
        return self.outbox.recover_interrupted()

    def cleanup_confirmed_local(self, sync_timestamp: float) -> int:
        """Delete only local points covered by a durable, current fleet acknowledgment.

        The supplied Unix timestamp is a caller cutoff; the synchronization run,
        outbox/policy rows, active fleet checkpoint, and exact fleet payload must
        independently agree before a local point is removed.
        """
        if not math.isfinite(sync_timestamp):
            raise ValueError("sync_timestamp must be finite")
        cutoff = datetime.fromtimestamp(sync_timestamp, timezone.utc)
        with self.db._lock:
            checkpoint_row = self.db._connection.execute(
                "SELECT value FROM sync_checkpoints WHERE checkpoint_id='fleet'"
            ).fetchone()
            run_rows = self.db._connection.execute(
                "SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-run:%'"
            ).fetchall()
        if checkpoint_row is None:
            return 0
        fleet_checkpoint = json.loads(checkpoint_row["value"])
        try:
            checkpoint_time = datetime.fromisoformat(fleet_checkpoint["timestamp"])
            if checkpoint_time.tzinfo is None:
                return 0
        except (KeyError, TypeError, ValueError):
            return 0

        confirmed: dict[str, dict[str, Any]] = {}
        for row in run_rows:
            run = json.loads(row["value"])
            if run.get("status") != SyncState.SYNCHRONIZED.value:
                continue
            try:
                completed_at = datetime.fromisoformat(run["updated_at"])
                if completed_at.tzinfo is None or completed_at > cutoff:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            if (run.get("fleet_generation") != fleet_checkpoint.get("generation")
                    or run.get("fleet_refresh_id") != fleet_checkpoint.get("refresh_id")
                    or checkpoint_time > completed_at):
                continue
            for entry in run.get("acknowledged", []):
                memory_id = entry.get("memory_id")
                if memory_id and entry.get("content_hash"):
                    confirmed[memory_id] = {**entry, "completed_at": completed_at}

        delete_local = getattr(self.store, "delete_local", None)
        if delete_local is None:
            return 0
        removed = 0
        for memory_id, entry in confirmed.items():
            local = self.store.retrieve(memory_id)
            fleet = self.store.retrieve_fleet(memory_id)
            if local is None or fleet is None:
                continue
            expected = (entry["memory_id"], entry["logical_id"], entry["revision"], entry["content_hash"])
            local_payload, fleet_payload = local.payload, fleet.payload
            local_identity = (local_payload.get("memory_id"), local_payload.get("logical_id"), local_payload.get("revision"), local_payload.get("content_hash"))
            fleet_identity = (fleet_payload.get("memory_id"), fleet_payload.get("logical_id"), fleet_payload.get("revision"), fleet_payload.get("content_hash"))
            if local.id != memory_id or fleet.id != memory_id or local_identity != expected or fleet_identity != expected:
                continue
            if local_payload.get("sensitivity") == Sensitivity.RESTRICTED.value or fleet_payload.get("sensitivity") == Sensitivity.RESTRICTED.value:
                continue
            with self.db._lock:
                policy = self.db._connection.execute(
                    "SELECT logical_id,revision,sync_policy,sync_state,sensitivity FROM memory_policy WHERE memory_id=?",
                    (memory_id,),
                ).fetchone()
                outbox = self.db._connection.execute(
                    "SELECT logical_id,revision,status FROM sync_outbox WHERE memory_id=?",
                    (memory_id,),
                ).fetchone()
                conflict = self.db._connection.execute(
                    "SELECT 1 FROM conflicts WHERE logical_id=? AND status IN ('OPEN','RESOLVING') LIMIT 1",
                    (entry["logical_id"],),
                ).fetchone()
            if (policy is None or outbox is None or conflict is not None
                    or policy["logical_id"] != entry["logical_id"] or policy["revision"] != entry["revision"]
                    or policy["sync_state"] != SyncState.SYNCHRONIZED.value
                    or policy["sync_policy"] != SyncPolicy.AUTO.value
                    or policy["sensitivity"] == Sensitivity.RESTRICTED.value
                    or outbox["logical_id"] != entry["logical_id"] or outbox["revision"] != entry["revision"]
                    or outbox["status"] != SyncState.SYNCHRONIZED.value):
                continue
            delete_local(memory_id)
            removed += 1
        return removed

    def _event(self, kind: str, message: str, memory_id: str | None = None, metadata: dict | None = None) -> None:
        self.activity.append(ActivityEvent(event_type=kind, device_id=self.device_id, memory_id=memory_id,
            timestamp=datetime.now(timezone.utc), message=message, metadata=metadata or {}))

    def _eligible(self, item: OutboxItem, allow_uploading: bool = False):
        record = self.memories.get(item.memory_id)
        if record is None:
            return None, "memory_missing"
        current = self.memories.current(item.logical_id)
        if current is None or current.memory_id != item.memory_id or current.revision != item.revision:
            return None, "superseded_revision"
        policy = self.memories.policy_workflow.get(item.memory_id) if self.memories.policy_workflow is not None else None
        sensitivity = Sensitivity(policy["sensitivity"]) if policy else record.sensitivity
        sync_policy = SyncPolicy(policy["sync_policy"]) if policy else record.sync_policy
        is_deleted = policy["is_deleted"] if policy else record.is_deleted
        if is_deleted or sensitivity is Sensitivity.RESTRICTED:
            return None, "privacy_restricted"
        if sync_policy is not SyncPolicy.AUTO:
            return None, "policy_not_auto"
        allowed_states = {SyncState.QUEUED, SyncState.RETRY_WAIT}
        if allow_uploading:
            allowed_states.add(SyncState.UPLOADING)
        if record.sync_state not in allowed_states:
            return None, "state_not_eligible"
        return record, None

    def _cancel(self, item: OutboxItem, reason: str) -> None:
        state = SyncState.SUPERSEDED if reason == "superseded_revision" else SyncState.LOCAL_ONLY
        self.outbox.cancel(item.id, state.value)

    async def run_once(self) -> SyncRunResult:
        if self._run_lock.locked():
            return SyncRunResult("RUNNING", pending=len(self.outbox.pending(self.batch_size)))
        async with self._run_lock:
            await self._blocking(self._scan_conflicts)
            items = self.outbox.claimable(self.batch_size)
            if not items and self.snapshots is None and not self._pending_retractions():
                return SyncRunResult("IDLE", pending=len(self.outbox.pending(self.batch_size)))
            health = await self._blocking(self.remote.health) if hasattr(self.remote, "health") else CloudHealth.ONLINE
            if health is not CloudHealth.ONLINE and str(health) != CloudHealth.ONLINE.value:
                return SyncRunResult(str(health), pending=len(self.outbox.pending(self.batch_size)))
            if items:
                self._event("SYNC_STARTED", "Queued memories are being synchronized", metadata={"count": len(items)})
            try:
                await self._blocking(self.remote.ensure_collection, self.embedding_dimension)
            except Exception as exc:
                return await self._fail_batch(items, exc)

            uploaded = failed = skipped = 0
            for item in items:
                try:
                    record, reason = self._eligible(item)
                except Exception as exc:
                    self.outbox.mark_uploading(item.id)
                    error = f"{type(exc).__name__}: {exc}"
                    retry = self.outbox.mark_retry(item.id, error)
                    self._event("SYNC_RETRY", "Eligibility check failed; retry scheduled", item.memory_id,
                        {"attempt": retry.retry_count, "error": error, "next_attempt_at": retry.next_attempt_at.isoformat() if retry.next_attempt_at else None})
                    failed += 1
                    continue
                if reason:
                    self._cancel(item, reason)
                    skipped += 1
                    continue
                self.outbox.mark_uploading(item.id)
                # Recheck persisted policy, privacy, and latest revision immediately before
                # reading the point that will cross the network boundary.
                try:
                    record, reason = self._eligible(item, allow_uploading=True)
                    point = self.store.retrieve(item.memory_id) if reason is None else None
                    # Recheck after local materialization so an intervening privacy/revision
                    # change cannot race the outbound call.
                    if reason is None:
                        record, reason = self._eligible(item, allow_uploading=True)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    retry = self.outbox.mark_retry(item.id, error)
                    self._event("SYNC_RETRY", "Local upload preparation failed; retry scheduled", item.memory_id,
                        {"attempt": retry.retry_count, "error": error, "next_attempt_at": retry.next_attempt_at.isoformat() if retry.next_attempt_at else None})
                    failed += 1
                    continue
                if reason or point is None:
                    state = SyncState.SUPERSEDED if reason == "superseded_revision" else SyncState.LOCAL_ONLY
                    self.outbox.cancel(item.id, state.value)
                    skipped += 1
                    continue
                # Project the effective SQLite policy over the original local
                # payload before it crosses the network boundary.
                payload = {**point.payload, **record.model_dump(mode="json"), "sync_state": SyncState.UPLOADED.value}
                point = StoredPoint(point.id, point.dense, point.sparse, payload)
                try:
                    await self._blocking(self.remote.upsert_point, point)
                    self.outbox.mark_uploaded(item.id)
                    uploaded += 1
                except Exception as exc:
                    self.outbox.mark_retry(item.id, f"{type(exc).__name__}: {exc}")
                    retry = next(outbox for outbox in self.outbox.all() if outbox.id == item.id)
                    self._event("SYNC_RETRY", "Remote upload failed; retry scheduled", item.memory_id,
                        {"attempt": retry.retry_count, "error": retry.last_error, "next_attempt_at": retry.next_attempt_at.isoformat() if retry.next_attempt_at else None})
                    failed += 1
            retraction_error = await self._process_retractions()
            if self.snapshots is not None:
                result = await self._refresh_and_confirm(uploaded, failed, skipped)
                await self._blocking(self._scan_conflicts)
                if result.refresh_error is None:
                    retraction_error = await self._confirm_retractions() or retraction_error
                if retraction_error and result.refresh_error is None:
                    result = SyncRunResult("DEGRADED", result.uploaded, result.failed, result.skipped, result.pending,
                        result.synchronized, result.snapshot_pending, retraction_error)
                return result
            # Without a fleet snapshot service the wait=True server delete is the only confirmation.
            retraction_error = await self._confirm_retractions(require_absent=False) or retraction_error
            if retraction_error:
                failed += 1
            return SyncRunResult("COMPLETED" if failed == 0 else "DEGRADED", uploaded, failed, skipped, len(self.outbox.pending(self.batch_size)))

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        with self.db._lock:
            rows = self.db._connection.execute(
                "SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-run:%' ORDER BY updated_at DESC,checkpoint_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["value"]) for row in rows]

    def _pending_runs(self) -> list[dict[str, Any]]:
        with self.db._lock:
            rows = self.db._connection.execute(
                "SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-run:%' ORDER BY updated_at,checkpoint_id"
            ).fetchall()
        return [run for row in rows if (run := json.loads(row["value"]))["status"] == SyncState.SNAPSHOT_PENDING.value]

    def _register_acknowledged_run(self) -> None:
        """Durably group acknowledged revisions; restart cannot create a second run."""
        now = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            existing = [json.loads(row["value"]) for row in conn.execute(
                "SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-run:%'"
            )]
            assigned = {entry["outbox_id"] for run in existing for entry in run["acknowledged"]}
            rows = [row for row in conn.execute(
                "SELECT * FROM sync_outbox WHERE status IN ('UPLOADED','SNAPSHOT_PENDING') ORDER BY created_at,id"
            ) if row["id"] not in assigned]
            if not rows:
                return
            entries = []
            for row in rows:
                point = self.store.retrieve(row["memory_id"])
                entries.append({"outbox_id": row["id"], "memory_id": row["memory_id"],
                    "logical_id": row["logical_id"], "revision": row["revision"],
                    "content_hash": point.payload.get("content_hash") if point else None})
                conn.execute("UPDATE sync_outbox SET status='SNAPSHOT_PENDING',updated_at=? WHERE id=?", (now,row["id"]))
                conn.execute("UPDATE memory_policy SET sync_state='SNAPSHOT_PENDING',updated_at=? WHERE memory_id=?", (now,row["memory_id"]))
            run_id = str(uuid5(NAMESPACE_URL, "grag-sync:" + ":".join(sorted(row["id"] for row in rows))))
            run = {"run_id":run_id,"status":SyncState.SNAPSHOT_PENDING.value,"acknowledged":entries,
                "started_at":min(row["created_at"] for row in rows),"updated_at":now,"completed_at":None}
            conn.execute("INSERT INTO sync_checkpoints(checkpoint_id,value,updated_at) VALUES(?,?,?)",
                ("sync-run:"+run_id,json.dumps(run,sort_keys=True),now))

    def _confirmed_checkpoint(self, result) -> dict[str, Any]:
        with self.db._lock:
            row = self.db._connection.execute("SELECT value FROM sync_checkpoints WHERE checkpoint_id='fleet'").fetchone()
        checkpoint = json.loads(row["value"]) if row else None
        if not checkpoint or not result.generation or not result.refresh_id or checkpoint.get("generation") != result.generation or checkpoint.get("refresh_id") != result.refresh_id:
            raise RuntimeError("Fleet refresh has no matching durable generation checkpoint")
        metadata = getattr(self.store, "fleet_snapshot_metadata", None)
        if metadata is not None:
            active = metadata()
            if not active or active.get("generation") != checkpoint["generation"] or active.get("refresh_id") != checkpoint["refresh_id"]:
                raise RuntimeError("Fleet checkpoint does not describe the active generation")
        return checkpoint

    def _complete_confirmed_runs(self, checkpoint: dict[str, Any]) -> int:
        synchronized = 0
        for run in self._pending_runs():
            for entry in run["acknowledged"]:
                point = self.store.retrieve_fleet(entry["memory_id"])
                payload = point.payload if point else {}
                if not point or point.id != entry["memory_id"] or payload.get("record_type") != "memory" or not entry["content_hash"] or any(
                    payload.get(key) != entry[key] for key in ("memory_id","logical_id","revision","content_hash")
                ):
                    break
            else:
                now = datetime.now(timezone.utc)
                with self.db.transaction() as conn:
                    row = conn.execute("SELECT value FROM sync_checkpoints WHERE checkpoint_id=?", ("sync-run:"+run["run_id"],)).fetchone()
                    current = json.loads(row["value"])
                    if current["status"] == SyncState.SYNCHRONIZED.value:
                        continue
                    for entry in current["acknowledged"]:
                        conn.execute("UPDATE sync_outbox SET status='SYNCHRONIZED',updated_at=? WHERE id=? AND status='SNAPSHOT_PENDING'", (now.isoformat(),entry["outbox_id"]))
                        conn.execute("UPDATE memory_policy SET sync_state='SYNCHRONIZED',updated_at=? WHERE memory_id=?", (now.isoformat(),entry["memory_id"]))
                    current.update(status=SyncState.SYNCHRONIZED.value,completed_at=now.isoformat(),updated_at=now.isoformat(),
                        fleet_generation=checkpoint["generation"],fleet_refresh_id=checkpoint["refresh_id"],last_error=None)
                    conn.execute("UPDATE sync_checkpoints SET value=?,updated_at=? WHERE checkpoint_id=?", (json.dumps(current,sort_keys=True),now.isoformat(),"sync-run:"+run["run_id"]))
                    ActivityLog.append_in_transaction(conn,ActivityEvent(
                        event_id=str(uuid5(NAMESPACE_URL,"sync-completed:"+run["run_id"])),event_type="SYNC_COMPLETED",
                        device_id=self.device_id,timestamp=now,message="Acknowledged memories are available in fleet memory",
                        metadata={"run_id":run["run_id"],"count":len(current["acknowledged"]),"generation":checkpoint["generation"]}))
                synchronized += len(run["acknowledged"])
        return synchronized

    async def _refresh_and_confirm(self, uploaded: int, failed: int, skipped: int) -> SyncRunResult:
        error = None
        synchronized = 0
        try:
            self._register_acknowledged_run()
            result = await self.snapshots.refresh()
            checkpoint = self._confirmed_checkpoint(result)
            synchronized = await self._blocking(self._complete_confirmed_runs, checkpoint)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            # The immutable upload acknowledgment and pending cohort survive any
            # network, apply, checkpoint, or final completion transaction failure.
            with self.db.transaction() as conn:
                for run in self._pending_runs():
                    run.update(last_error=error,updated_at=datetime.now(timezone.utc).isoformat())
                    conn.execute("UPDATE sync_checkpoints SET value=?,updated_at=? WHERE checkpoint_id=?",
                        (json.dumps(run,sort_keys=True),run["updated_at"],"sync-run:"+run["run_id"]))
        pending = len(self.outbox.pending(self.batch_size))
        snapshot_pending = sum(item.status in ("UPLOADED","SNAPSHOT_PENDING") for item in self.outbox.all())
        status = "DEGRADED" if failed or error else "SNAPSHOT_PENDING" if snapshot_pending else "COMPLETED"
        return SyncRunResult(status,uploaded,failed,skipped,pending,synchronized,snapshot_pending,error)

    _SCAN_STATES = (SyncState.NEW, SyncState.LOCAL_DIRTY, SyncState.LOCAL_ONLY, SyncState.AWAITING_APPROVAL,
                    SyncState.QUEUED, SyncState.UPLOADING, SyncState.RETRY_WAIT, SyncState.UPLOADED,
                    SyncState.SNAPSHOT_PENDING, SyncState.SYNCHRONIZED, SyncState.CONFLICTED)
    _BLOCKABLE = ("QUEUED", "RETRY_WAIT", "UPLOADING")

    def _own_memory_ids(self, logical_id: str) -> set[str]:
        with self.db._lock:
            rows = self.db._connection.execute("SELECT memory_id FROM memory_policy WHERE logical_id=?", (logical_id,)).fetchall()
        return {row["memory_id"] for row in rows}

    def _scan_conflicts(self) -> int:
        """Detect divergence between the local head and fleet branch tips.

        Uses retained lineage only: this device's own committed revision IDs prove
        a fleet copy is its ancestor even after local cleanup, and revision numbers
        never choose a winner. Settled heads are scanned too, because another
        branch can reach fleet after both uploads.
        """
        list_fleet = getattr(self.store, "list_fleet_points", None)
        if self.conflicts is None or list_fleet is None:
            return 0
        local_records = self.memories._records()
        heads: dict[str, Any] = {}
        for record in local_records:
            if record.logical_id not in heads or heads[record.logical_id].revision < record.revision:
                heads[record.logical_id] = record
        fleet_by_logical: dict[str, list[Any]] = {}
        for point in list_fleet():
            if point.payload.get("record_type") == "memory":
                try:
                    fleet_by_logical.setdefault(point.payload["logical_id"], []).append(MemoryRecord.model_validate(point.payload))
                except Exception:
                    continue
        found = 0
        for logical_id, local in heads.items():
            fleet_records = fleet_by_logical.get(logical_id)
            if not fleet_records or local.is_deleted or local.sync_state not in self._SCAN_STATES:
                continue
            own_ids = self._own_memory_ids(logical_id)
            local_history = [r for r in local_records if r.logical_id == logical_id]
            local_history += [r for r in fleet_records if r.memory_id in own_ids and r.memory_id not in {h.memory_id for h in local_history}]
            tips = [r for r in fleet_records if not any(c.parent_revision == r.revision and c.revision > r.revision for c in fleet_records)]
            for fleet in sorted(tips, key=lambda r: (r.revision, r.memory_id)):
                if fleet.memory_id == local.memory_id:
                    continue
                conflict = self.conflicts.detect(local, fleet, local_history=local_history, fleet_history=fleet_records)
                if conflict is None or self.conflicts.get(conflict.conflict_id).status not in ("OPEN", "RESOLVING"):
                    continue
                found += 1
                for item in self.outbox.all():
                    if item.memory_id == local.memory_id and item.status in self._BLOCKABLE:
                        self.outbox.cancel(item.id, SyncState.CONFLICTED.value)
                with self.db.transaction() as conn:
                    conn.execute("UPDATE memory_policy SET sync_state='CONFLICTED',updated_at=? WHERE memory_id=? "
                                 "AND sync_state NOT IN ('SUPERSEDED','UPLOADED','SNAPSHOT_PENDING')",
                                 (datetime.now(timezone.utc).isoformat(), local.memory_id))
        return found

    def _pending_retractions(self) -> list[dict[str, Any]]:
        with self.db._lock:
            rows = self.db._connection.execute(
                "SELECT value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-retraction:%' ORDER BY updated_at,checkpoint_id"
            ).fetchall()
        return [job for row in rows if (job := json.loads(row["value"]))["status"] != "COMPLETED"]

    def _save_retraction(self, job: dict[str, Any], **changes: Any) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        job = {**job, **changes, "updated_at": now}
        with self.db.transaction() as conn:
            conn.execute("UPDATE sync_checkpoints SET value=?,updated_at=? WHERE checkpoint_id=?",
                (json.dumps(job, sort_keys=True), now, "sync-retraction:" + job["retraction_id"]))
        return job

    def _archive_fleet_copies(self, target_ids: list[str]) -> None:
        """Keep immutable local history before remote withdrawal removes fleet copies."""
        for memory_id in target_ids:
            if self.store.retrieve(memory_id) is None:
                fleet = self.store.retrieve_fleet(memory_id)
                if fleet is not None and fleet.payload.get("record_type") == "memory":
                    self.store.upsert(fleet)

    async def _process_retractions(self) -> str | None:
        """Idempotently delete exact remote IDs; only IDs, never memory content, are sent."""
        error = None
        for job in self._pending_retractions():
            try:
                await self._blocking(self._archive_fleet_copies, job["target_ids"])
                await self._blocking(self.remote.delete_points, job["target_ids"])
                self._save_retraction(job, status="DELETED_REMOTE", attempts=job["attempts"] + 1, last_error=None)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._save_retraction(job, attempts=job["attempts"] + 1, last_error=error)
        return error

    async def _confirm_retractions(self, require_absent: bool = True) -> str | None:
        """Complete a job only after a refreshed fleet no longer contains its targets."""
        error = None
        for job in self._pending_retractions():
            if job["status"] != "DELETED_REMOTE":
                continue
            if require_absent and any(self.store.retrieve_fleet(memory_id) is not None for memory_id in job["target_ids"]):
                error = "RetractionNotConfirmed: fleet still contains retracted memory IDs"
                self._save_retraction(job, status="QUEUED", last_error=error)
                continue
            await self._blocking(self._finish_retraction, job)
        return error

    def _finish_retraction(self, job: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        targets = set(job["target_ids"])
        with self.db.transaction() as conn:
            for memory_id in targets:
                conn.execute("UPDATE sync_outbox SET status='SUPERSEDED',updated_at=? WHERE memory_id=? AND status IN ('UPLOADED','SNAPSHOT_PENDING')", (now, memory_id))
                conn.execute("UPDATE memory_policy SET sync_state='SUPERSEDED',updated_at=? WHERE memory_id=? AND sync_state IN ('UPLOADED','SNAPSHOT_PENDING')", (now, memory_id))
            for row in conn.execute("SELECT checkpoint_id,value FROM sync_checkpoints WHERE checkpoint_id LIKE 'sync-run:%'").fetchall():
                run = json.loads(row["value"])
                if run["status"] != SyncState.SNAPSHOT_PENDING.value:
                    continue
                kept = [entry for entry in run["acknowledged"] if entry["memory_id"] not in targets]
                if len(kept) == len(run["acknowledged"]):
                    continue
                run.update(acknowledged=kept, updated_at=now)
                if not kept:
                    run.update(status=SyncState.SUPERSEDED.value, completed_at=now)
                conn.execute("UPDATE sync_checkpoints SET value=?,updated_at=? WHERE checkpoint_id=?", (json.dumps(run, sort_keys=True), now, row["checkpoint_id"]))
            job = {**job, "status": "COMPLETED", "completed_at": now, "updated_at": now, "last_error": None}
            conn.execute("UPDATE sync_checkpoints SET value=?,updated_at=? WHERE checkpoint_id=?",
                (json.dumps(job, sort_keys=True), now, "sync-retraction:" + job["retraction_id"]))

    async def _fail_batch(self, items: list[OutboxItem], exc: Exception) -> SyncRunResult:
        failed = 0
        for item in items:
            record, reason = self._eligible(item)
            if reason:
                self._cancel(item, reason)
                continue
            self.outbox.mark_uploading(item.id)
            self.outbox.mark_retry(item.id, f"{type(exc).__name__}: {exc}")
            self._event("SYNC_RETRY", "Remote collection setup failed; retry scheduled", item.memory_id,
                {"error": str(exc)})
            failed += 1
        return SyncRunResult("DEGRADED", failed=failed, pending=len(self.outbox.pending(self.batch_size)))
