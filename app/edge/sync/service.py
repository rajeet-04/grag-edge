"""Idempotent worker that uploads only the current eligible edge revision."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.edge.memory.models import Sensitivity, SyncPolicy, SyncState
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


class SyncService:
    def __init__(self, store: Any, memories: Any, outbox: SyncOutbox, db: EdgeStateDB, activity: ActivityLog, remote: Any, device_id: str, embedding_dimension: int = 768, batch_size: int = 50):
        self.store, self.memories, self.outbox = store, memories, outbox
        self.db, self.activity, self.remote = db, activity, remote
        self.device_id, self.embedding_dimension, self.batch_size = device_id, embedding_dimension, batch_size
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
            items = self.outbox.claimable(self.batch_size)
            if not items:
                return SyncRunResult("IDLE", pending=len(self.outbox.pending(self.batch_size)))
            health = await self._blocking(self.remote.health) if hasattr(self.remote, "health") else CloudHealth.ONLINE
            if health is not CloudHealth.ONLINE and str(health) != CloudHealth.ONLINE.value:
                return SyncRunResult(str(health), pending=len(self.outbox.pending(self.batch_size)))
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
            return SyncRunResult("COMPLETED" if failed == 0 else "DEGRADED", uploaded, failed, skipped, len(self.outbox.pending(self.batch_size)))

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
