"""Revision and provenance rules for edge memories."""
from __future__ import annotations

import hashlib
import asyncio
from typing import Any
from uuid import uuid4

from app.edge.memory.bm25 import EdgeBm25Indexer
from app.edge.memory.models import CreateMemory, MemoryRecord, ReviseMemory, SyncState, utcnow
from app.edge.memory.store import StoredPoint
from app.llm.embedding import get_embedding_service


class MemoryService:
    def __init__(self, store: Any, embedding_service: Any | None = None) -> None:
        self.store = store
        self.embedding_service = embedding_service or get_embedding_service()
        self.bm25 = EdgeBm25Indexer(store)
        self._write_lock = asyncio.Lock()

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _records(self) -> list[MemoryRecord]:
        points = self.store.list_points()
        return [MemoryRecord.model_validate(p.payload) for p in points if p.payload.get("record_type") == "memory"]

    def _all_records(self) -> list[MemoryRecord]:
        records = self._records()
        list_fleet = getattr(self.store, "list_fleet_points", None)
        if list_fleet is not None:
            records.extend(MemoryRecord.model_validate(p.payload) for p in list_fleet() if p.payload.get("record_type") == "memory")
        return records

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
            record = MemoryRecord(**command.model_dump(exclude={"memory_id", "logical_id"}), memory_id=memory_id, logical_id=logical_id,
                created_at=now, updated_at=now, revision=1, parent_revision=None, content_hash=self.content_hash(command.content))
            return await self._write(record)

    async def revise(self, logical_id: str, command: ReviseMemory) -> MemoryRecord:
        async with self._write_lock:
            current = self.current(logical_id)
            if current is None:
                raise KeyError(logical_id)
            if current.revision != command.parent_revision:
                raise ValueError(f"stale parent_revision {command.parent_revision}; current revision is {current.revision}")
            values = current.model_dump()
            for key, value in command.model_dump(exclude={"content", "parent_revision"}, exclude_unset=True).items():
                if value is not None:
                    values[key] = value
            now = utcnow()
            values.update(memory_id=str(uuid4()), content=command.content, updated_at=now,
                revision=current.revision + 1, parent_revision=current.revision, content_hash=self.content_hash(command.content), is_deleted=False)
            record = MemoryRecord(**values)
            return await self._write(record)

    def get(self, memory_id: str) -> MemoryRecord | None:
        try:
            point = self.store.retrieve(memory_id)
            if point is None:
                point = self.store.retrieve_fleet(memory_id)
        except ValueError:
            return None
        return MemoryRecord.model_validate(point.payload) if point and point.payload.get("record_type") == "memory" else None

    def history(self, logical_id: str) -> list[MemoryRecord]:
        return sorted((r for r in self._records() if r.logical_id == logical_id), key=lambda r: r.revision)

    def current(self, logical_id: str) -> MemoryRecord | None:
        records = self.history(logical_id)
        return max(records, key=lambda r: r.revision) if records and not max(records, key=lambda r: r.revision).is_deleted else None

    async def tombstone(self, logical_id: str) -> MemoryRecord:
        async with self._write_lock:
            current = self.current(logical_id)
            if current is None:
                raise KeyError(logical_id)
            now = utcnow()
            record = current.model_copy(update={"memory_id": str(uuid4()), "updated_at": now, "revision": current.revision + 1,
                "parent_revision": current.revision, "is_deleted": True, "content_hash": self.content_hash(current.content)})
            return await self._write(record)

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
