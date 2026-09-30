"""Revision and provenance rules for edge memories."""
from __future__ import annotations

import hashlib
import asyncio
from typing import Any
from uuid import uuid4

from app.edge.memory.bm25 import EdgeBm25Indexer
from app.edge.memory.models import CreateMemory, MemoryRecord, ReviseMemory, SyncPolicy, SyncState, utcnow
from app.edge.policy.engine import SyncDecision, SyncPolicyEngine
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.workflow import PolicyWorkflow
from app.edge.memory.store import StoredPoint
from app.llm.embedding import get_embedding_service


class MemoryService:
    def __init__(self, store: Any, embedding_service: Any | None = None, state_db: EdgeStateDB | None = None) -> None:
        self.store = store
        self.embedding_service = embedding_service or get_embedding_service()
        self.bm25 = EdgeBm25Indexer(store)
        self._write_lock = asyncio.Lock()
        self.state_db = state_db
        self.policy_engine = SyncPolicyEngine()
        self.policy_workflow = PolicyWorkflow(state_db) if state_db is not None else None

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _records(self) -> list[MemoryRecord]:
        points = self.store.list_points()
        return [self._overlay(MemoryRecord.model_validate(p.payload)) for p in points if p.payload.get("record_type") == "memory"]

    def _all_records(self) -> list[MemoryRecord]:
        records = self._records()
        list_fleet = getattr(self.store, "list_fleet_points", None)
        if list_fleet is not None:
            records.extend(self._overlay(MemoryRecord.model_validate(p.payload)) for p in list_fleet() if p.payload.get("record_type") == "memory")
        return records

    def _overlay(self, record: MemoryRecord) -> MemoryRecord:
        if self.policy_workflow is None:
            return record
        policy = self.policy_workflow.get(record.memory_id)
        if policy is None:
            return record
        return record.model_copy(update={
            "requested_sync_policy": SyncPolicy(policy["requested_sync_policy"]) if policy["requested_sync_policy"] else None,
            "sync_policy": SyncPolicy(policy["sync_policy"]),
            "sync_state": SyncState(policy["sync_state"]),
            "sync_reason_codes": policy["sync_reason_codes"],
            "is_deleted": policy["is_deleted"],
        })

    @staticmethod
    def _decision_state(record: MemoryRecord, decision: SyncDecision) -> SyncState:
        if record.is_deleted or decision.action is SyncPolicy.LOCAL_ONLY:
            return SyncState.LOCAL_ONLY
        if decision.action is SyncPolicy.APPROVAL_REQUIRED:
            return SyncState.AWAITING_APPROVAL
        return SyncState.QUEUED

    def _commit_policy(
        self, record: MemoryRecord, event_type: str, deleted: bool = False,
        force_state: SyncState | None = None,
    ) -> MemoryRecord:
        if self.policy_workflow is None:
            return record
        decision = (
            SyncDecision(SyncPolicy.LOCAL_ONLY, ("tombstone_local_only",))
            if deleted
            else self.policy_engine.evaluate(record)
        )
        state = force_state or self._decision_state(record, decision)
        self.policy_workflow.commit_record(record, decision, state, event_type)
        return self._overlay(record)

    async def _write(self, record: MemoryRecord) -> MemoryRecord:
        dense = await self.embedding_service.embed_with_context(record.content, "search_document")
        sparse = self.bm25.embed_document(record.content)
        self.store.upsert(StoredPoint(record.memory_id, dense, sparse, {"record_type": "memory", **record.model_dump(mode="json")}))
        return record

    async def create(self, command: CreateMemory) -> MemoryRecord:
        async with self._write_lock:
            memory_id = str(command.memory_id or uuid4())
            logical_id = str(command.logical_id or uuid4())
            if self.store.retrieve(memory_id) is not None or self.store.retrieve_fleet(memory_id) is not None:
                raise ValueError("memory_id already exists")
            if any(record.logical_id == logical_id for record in self._all_records()):
                raise ValueError("logical_id already exists")
            now = utcnow()
            requested_policy = command.sync_policy if "sync_policy" in command.model_fields_set else None
            record = MemoryRecord(**command.model_dump(exclude={"memory_id", "logical_id", "sync_policy"}), memory_id=memory_id, logical_id=logical_id,
                created_at=now, updated_at=now, revision=1, parent_revision=None, content_hash=self.content_hash(command.content),
                requested_sync_policy=requested_policy)
            stored = await self._write(record)
            return self._commit_policy(stored, "MEMORY_CREATED")

    async def revise(self, logical_id: str, command: ReviseMemory) -> MemoryRecord:
        async with self._write_lock:
            current = self.current(logical_id)
            if current is None:
                raise KeyError(logical_id)
            if current.revision != command.parent_revision:
                raise ValueError(f"stale parent_revision {command.parent_revision}; current revision is {current.revision}")
            values = current.model_dump()
            for key, value in command.model_dump(exclude={"content", "parent_revision"}, exclude_unset=True).items():
                if key == "sync_policy":
                    continue
                if value is not None:
                    values[key] = value
            values["requested_sync_policy"] = command.sync_policy if "sync_policy" in command.model_fields_set else current.requested_sync_policy
            values["sync_policy"] = SyncPolicy.LOCAL_ONLY
            values["sync_state"] = SyncState.LOCAL_DIRTY
            values["sync_reason_codes"] = ()
            now = utcnow()
            values.update(memory_id=str(uuid4()), content=command.content, updated_at=now,
                revision=current.revision + 1, parent_revision=current.revision, content_hash=self.content_hash(command.content), is_deleted=False)
            record = MemoryRecord(**values)
            stored = await self._write(record)
            return self._commit_policy(stored, "MEMORY_REVISED")

    def get(self, memory_id: str) -> MemoryRecord | None:
        try:
            point = self.store.retrieve(memory_id)
            if point is None:
                point = self.store.retrieve_fleet(memory_id)
        except ValueError:
            return None
        return self._overlay(MemoryRecord.model_validate(point.payload)) if point and point.payload.get("record_type") == "memory" else None

    def history(self, logical_id: str) -> list[MemoryRecord]:
        return sorted((r for r in self._all_records() if r.logical_id == logical_id), key=lambda r: (r.revision, r.memory_id))

    def current(self, logical_id: str) -> MemoryRecord | None:
        # Mutations are based only on the writable local branch. Fleet-only
        # revisions are copied into a new local revision by explicit conflict resolution.
        records = [record for record in self._records() if record.logical_id == logical_id]
        return max(records, key=lambda r: r.revision) if records and not max(records, key=lambda r: r.revision).is_deleted else None

    async def tombstone(self, logical_id: str) -> MemoryRecord:
        async with self._write_lock:
            current = self.current(logical_id)
            if current is None:
                raise KeyError(logical_id)
            now = utcnow()
            record = current.model_copy(update={"memory_id": str(uuid4()), "updated_at": now, "revision": current.revision + 1,
                "parent_revision": current.revision, "is_deleted": True, "content_hash": self.content_hash(current.content),
                "sync_policy": SyncPolicy.LOCAL_ONLY, "sync_state": SyncState.LOCAL_DIRTY, "sync_reason_codes": ()})
            stored = await self._write(record)
            return self._commit_policy(stored, "MEMORY_REVISED", deleted=True)

    async def approve(self, memory_id: str) -> MemoryRecord:
        async with self._write_lock:
            record = self.get(memory_id)
            if record is None:
                raise KeyError(memory_id)
            if not any(item.memory_id == record.memory_id for item in self.history(record.logical_id)):
                raise ValueError("fleet memories are read-only")
            current = self.current(record.logical_id)
            if current is None or current.memory_id != record.memory_id:
                raise ValueError("approval target is not current")
            if record.is_deleted:
                raise ValueError("deleted memories cannot be approved")
            if self.policy_workflow is None:
                raise RuntimeError("sync policy state is not configured")
            return self._overlay_from_policy(record, self.policy_workflow.transition_approval(record, approve=True))

    async def reject(self, memory_id: str) -> MemoryRecord:
        async with self._write_lock:
            record = self.get(memory_id)
            if record is None:
                raise KeyError(memory_id)
            if not any(item.memory_id == record.memory_id for item in self.history(record.logical_id)):
                raise ValueError("fleet memories are read-only")
            current = self.current(record.logical_id)
            if current is None or current.memory_id != record.memory_id:
                raise ValueError("reject target is not current")
            if self.policy_workflow is None:
                raise RuntimeError("sync policy state is not configured")
            return self._overlay_from_policy(record, self.policy_workflow.transition_approval(record, approve=False))

    @staticmethod
    def _overlay_from_policy(record: MemoryRecord, policy: dict[str, Any]) -> MemoryRecord:
        return record.model_copy(update={
            "requested_sync_policy": SyncPolicy(policy["requested_sync_policy"]) if policy["requested_sync_policy"] else None,
            "sync_policy": SyncPolicy(policy["sync_policy"]), "sync_state": SyncState(policy["sync_state"]),
            "sync_reason_codes": policy["sync_reason_codes"], "is_deleted": policy["is_deleted"],
        })

    async def reconcile(self) -> None:
        if self.policy_workflow is None:
            return
        async with self._write_lock:
            records = [
                MemoryRecord.model_validate(point.payload)
                for point in self.store.list_points()
                if point.payload.get("record_type") == "memory"
            ]
            records.sort(key=lambda record: (record.logical_id, record.revision, record.memory_id))
            latest_by_logical: dict[str, int] = {}
            for record in records:
                latest_by_logical[record.logical_id] = max(
                    latest_by_logical.get(record.logical_id, 0), record.revision
                )
            for record in records:
                if self.policy_workflow.get(record.memory_id) is None:
                    is_superseded = record.revision < latest_by_logical[record.logical_id]
                    self._commit_policy(
                        record,
                        "MEMORY_CREATED" if record.revision == 1 else "MEMORY_REVISED",
                        deleted=record.is_deleted,
                        force_state=SyncState.SUPERSEDED if is_superseded else None,
                    )

    def list(self, **filters: Any) -> list[MemoryRecord]:
        current: dict[str, MemoryRecord] = {}
        for record in self._all_records():
            if record.logical_id not in current or current[record.logical_id].revision < record.revision:
                current[record.logical_id] = record
        result = [record for record in current.values() if not record.is_deleted]
        for name, value in filters.items():
            if value is None:
                continue
            if name == "tag":
                result = [r for r in result if value in r.tags]
            elif name == "from_time":
                result = [r for r in result if r.updated_at >= value]
            elif name == "to_time":
                result = [r for r in result if r.updated_at <= value]
            elif name in MemoryRecord.model_fields:
                result = [r for r in result if getattr(r, name) == value]
        return sorted(result, key=lambda r: (r.updated_at, r.memory_id), reverse=True)
