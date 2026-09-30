"""Explicit conflict inspection and resolution."""
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.edge.api.memories import runtime
from app.edge.conflicts import ConflictRecord
from app.edge.conflicts.service import ConflictResolutionError, RESOLUTIONS

router = APIRouter(prefix="/edge", tags=["edge-conflicts"])


class ResolveRequest(BaseModel):
    resolution: str
    merged_content: str | None = None


@router.get("/conflicts", response_model=list[ConflictRecord])
def list_conflicts(request: Request):
    return runtime(request).conflicts.list_open()


@router.get("/conflicts/{conflict_id}")
def get_conflict(conflict_id: str, request: Request):
    edge = runtime(request)
    conflict = edge.conflicts.get(conflict_id)
    if conflict is None:
        raise HTTPException(404, "conflict not found")
    return {
        "conflict": conflict,
        "local": edge.memories.get(conflict.local_memory_id),
        "fleet": edge.memories.get(conflict.fleet_memory_id),
        "history": edge.memories.history(conflict.logical_id),
    }


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictRecord)
async def resolve_conflict(conflict_id: str, body: ResolveRequest, request: Request):
    if body.resolution not in RESOLUTIONS:
        raise HTTPException(422, "resolution must be one of " + ", ".join(sorted(RESOLUTIONS)))
    edge = runtime(request)
    try:
        return await edge.conflicts.resolve(conflict_id, body.resolution, edge.memories, body.merged_content)
    except KeyError as exc:
        raise HTTPException(404, "conflict not found") from exc
    except ConflictResolutionError as exc:
        raise HTTPException(409 if "already" in str(exc) or "unavailable" in str(exc) else 422, str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "sync state is temporarily unavailable") from exc
