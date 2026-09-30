"""Operational status, activity history, counters, and persisted SSE events."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.edge.api.memories import runtime

router = APIRouter(prefix="/edge", tags=["edge-operations"])


@router.get("/status")
def edge_status(request: Request):
    edge = runtime(request)
    connectivity = edge.connectivity.current()
    return {"status": "READY", "device_id": edge.device_id, **connectivity}


@router.get("/activity")
def activity(request: Request, limit: int = 100, before: datetime | None = None):
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit must be between 1 and 500")
    return runtime(request).activity.list(limit, before)


@router.get("/stats")
def stats(request: Request):
    edge = runtime(request)
    local = [p for p in edge.store.list_points() if p.payload.get("record_type") == "memory"]
    fleet = [p for p in edge.store.list_fleet_points() if p.payload.get("record_type") == "memory"]
    items = edge.outbox.all()
    last_sync = max((item.updated_at for item in items if item.status == "SYNCHRONIZED"), default=None)
    return {
        "local_memory_count": len(local),
        "fleet_memory_count": len(fleet),
        "pending_sync": sum(item.status in ("QUEUED", "RETRY_WAIT", "UPLOADING", "UPLOADED", "SNAPSHOT_PENDING") for item in items),
        "last_sync": last_sync.isoformat() if last_sync else None,
        "sync_success_count": sum(item.status == "SYNCHRONIZED" for item in items),
        "open_conflict_count": edge.conflicts.open_count(),
        "sync_failure_count": sum(item.retry_count for item in items),
        "search_latency_ms": None,
        "connectivity": edge.connectivity.current()["connectivity"],
    }


@router.get("/events")
async def events(request: Request):
    edge = runtime(request)
    cursor = request.headers.get("last-event-id") or None

    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            batch = edge.activity.after(cursor, 100)
            if batch:
                for event in batch:
                    cursor = event.event_id
                    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
                    yield f"id: {event.event_id}\nevent: {event.event_type}\ndata: {payload}\n\n"
            else:
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
