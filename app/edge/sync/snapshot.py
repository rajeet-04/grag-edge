"""Stream cloud snapshots and checkpoint only published fleet generations."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote

import httpx

from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB


@dataclass(frozen=True, slots=True)
class FleetRefreshResult:
    status: str
    generation: str | None = None
    refresh_id: str | None = None


class FleetSnapshotService:
    def __init__(self, store, db: EdgeStateDB, activity: ActivityLog, device_id: str,
                 url: str, collection: str, api_key: str | None = None,
                 client: httpx.AsyncClient | None = None):
        self.store, self.db, self.activity, self.device_id = store, db, activity, device_id
        self.base_url = url.rstrip("/") + "/collections/" + quote(collection, safe="") + "/shards/0/snapshot"
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5), headers={"api-key": api_key} if api_key else {})
        self._lock = asyncio.Lock()

    def reconcile_checkpoint(self) -> None:
        metadata = self.store.fleet_snapshot_metadata()
        if metadata is None:
            return
        now = metadata["timestamp"]
        event = ActivityEvent(event_id=metadata["refresh_id"], event_type="FLEET_REFRESH_COMPLETED",
            device_id=self.device_id, timestamp=datetime.fromisoformat(now),
            message="Fleet snapshot generation published", metadata=metadata)
        with self.db.transaction() as conn:
            conn.execute("INSERT INTO sync_checkpoints(checkpoint_id,value,updated_at) VALUES('fleet',?,?) "
                "ON CONFLICT(checkpoint_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (json.dumps(metadata, sort_keys=True), now))
            ActivityLog.append_in_transaction(conn, event)

    async def _download(self, method: str, url: str, manifest=None) -> Path:
        fd, name = tempfile.mkstemp(suffix=".part", prefix="grag-fleet-")
        path = Path(name)
        try:
            with os.fdopen(fd, "wb") as file:
                async with self.client.stream(method, url, json=manifest if method == "POST" else None) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        file.write(chunk)
                file.flush()
                os.fsync(file.fileno())
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def bootstrap_if_missing(self) -> FleetRefreshResult:
        async with self._lock:
            if self.store.fleet_snapshot_metadata() is not None:
                self.reconcile_checkpoint()
                return self._result("UNCHANGED")
            return await self._bootstrap()

    def _result(self, status: str) -> FleetRefreshResult:
        metadata = self.store.fleet_snapshot_metadata() or {}
        return FleetRefreshResult(status, metadata.get("generation"), metadata.get("refresh_id"))

    def _started(self) -> None:
        self.activity.append(ActivityEvent(event_type="FLEET_REFRESH_STARTED", device_id=self.device_id,
            timestamp=datetime.now(timezone.utc), message="Fleet snapshot refresh started"))

    async def _bootstrap(self) -> FleetRefreshResult:
        self._started()
        path = await self._download("GET", self.base_url)
        try:
            await asyncio.to_thread(self.store.replace_fleet_from_snapshot, path)
            self.reconcile_checkpoint()
            return self._result("COMPLETED")
        finally:
            path.unlink(missing_ok=True)

    async def close(self) -> None:
        await self.client.aclose()
