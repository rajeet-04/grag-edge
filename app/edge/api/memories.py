"""Memory inspection and hybrid search endpoints."""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from app.edge.memory.models import CreateMemory, MemoryRecord, MemoryType, Importance, SyncState, ReviseMemory
from app.edge.memory.hybrid_search import SearchMode

router = APIRouter(prefix="/edge", tags=["edge-memory"])

class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: SearchMode = SearchMode.HYBRID
    limit: int = Field(default=10, gt=0, le=100)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value


def runtime(request: Request):
    value = getattr(request.app.state, "edge_runtime", None)
    if value is None:
        raise HTTPException(503, "edge runtime is not available")
    return value

@router.post("/memories", response_model=MemoryRecord, status_code=201)
async def create_memory(command: CreateMemory, request: Request):
    try:
        return await runtime(request).memories.create(command)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get("/memories", response_model=list[MemoryRecord])
def list_memories(request: Request, source: str | None = None, memory_type: MemoryType | None = None,
    sync_state: SyncState | None = None, importance: Importance | None = None, device_id: str | None = None,
    tag: str | None = None, from_time: datetime | None = None, to_time: datetime | None = None):
    if (from_time is not None and from_time.utcoffset() is None) or (to_time is not None and to_time.utcoffset() is None):
        raise HTTPException(422, "timestamps must include a timezone")
    return runtime(request).memories.list(source_type=source, memory_type=memory_type, sync_state=sync_state,
        importance=importance, device_id=device_id, tag=tag, from_time=from_time, to_time=to_time)

@router.get("/memories/{memory_id}", response_model=MemoryRecord)
def get_memory(memory_id: str, request: Request):
    record = runtime(request).memories.get(memory_id)
    if record is None:
        raise HTTPException(404, "memory not found")
    return record

@router.patch("/memories/{memory_id}", response_model=MemoryRecord)
async def revise_memory(memory_id: str, command: ReviseMemory, request: Request):
    service = runtime(request).memories
    previous = service.get(memory_id)
    if previous is None:
        raise HTTPException(404, "memory not found")
    if previous.is_deleted:
        raise HTTPException(409, "deleted memories cannot be revised")
    try:
        return await service.revise(previous.logical_id, command)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(409, "memory is no longer current") from exc

@router.post("/search")
async def search_memories(command: SearchRequest, request: Request):
    hits = await runtime(request).search.search(command.query, command.mode, command.limit)
    service = runtime(request).memories
    results = []
    for hit in hits:
        record = service.get(hit.point_id)
        if record is None:
            continue
        results.append({"memory_id": hit.point_id, "origin": hit.origin, "score": hit.score, "dense_score": hit.dense_score,
            "sparse_score": hit.sparse_score, "revision": record.revision, "sync_state": record.sync_state,
            "content": record.content, "device_id": record.device_id, "source_type": record.source_type, "source_id": record.source_id})
    return {"results": results}
