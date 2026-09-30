"""Operator controls and inspection for the durable synchronization queue."""
import sqlite3

from fastapi import APIRouter, HTTPException, Request

from app.edge.api.memories import runtime

router = APIRouter(prefix="/edge/sync", tags=["edge-sync"])


async def _transition(request: Request, memory_id: str, approve: bool):
    service = runtime(request).memories
    try:
        return await (service.approve(memory_id) if approve else service.reject(memory_id))
    except KeyError as exc:
        raise HTTPException(404, "memory not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "sync state is temporarily unavailable") from exc


@router.post("/{memory_id}/approve")
async def approve(memory_id: str, request: Request):
    return await _transition(request, memory_id, True)


@router.post("/{memory_id}/reject")
async def reject(memory_id: str, request: Request):
    return await _transition(request, memory_id, False)


@router.get("/queue")
def queue(request: Request, limit: int = 100):
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit must be between 1 and 500")
    return runtime(request).outbox.pending(limit)
