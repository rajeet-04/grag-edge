"""Poll cloud reachability and persist device connectivity transitions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.server_client import CloudHealth


class ConnectivityState(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class ConnectivityMonitor:
    def __init__(self, client: Any, db: EdgeStateDB, activity: ActivityLog, device_id: str):
        self.client = client
        self.db = db
        self.activity = activity
        self.device_id = device_id

    def current(self) -> dict[str, Any]:
        with self.db._lock:
            row = self.db._connection.execute("SELECT state_json FROM device_state WHERE device_id=?", (self.device_id,)).fetchone()
        if row is None:
            return {"device_id": self.device_id, "connectivity": ConnectivityState.UNKNOWN.value, "connectivity_changed_at": None}
        return json.loads(row["state_json"])

    def run_once(self) -> ConnectivityState:
        observed = self.client.health()
        state = ConnectivityState(observed.value if isinstance(observed, CloudHealth) else str(observed))
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            row = conn.execute("SELECT state_json FROM device_state WHERE device_id=?", (self.device_id,)).fetchone()
            previous = json.loads(row["state_json"]) if row else {"connectivity": ConnectivityState.UNKNOWN.value}
            previous_state = ConnectivityState(previous.get("connectivity", "UNKNOWN"))
            changed_at = previous.get("connectivity_changed_at")
            if previous_state is not state:
                changed_at = now.isoformat()
            current = {**previous, "device_id": self.device_id, "connectivity": state.value, "connectivity_changed_at": changed_at}
            conn.execute(
                "INSERT INTO device_state(device_id,state_json,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at",
                (self.device_id, json.dumps(current, sort_keys=True), now.isoformat()),
            )
            if previous_state is not state and state in (ConnectivityState.ONLINE, ConnectivityState.OFFLINE):
                kind = "CLOUD_LINK_UP" if state is ConnectivityState.ONLINE else "CLOUD_LINK_DOWN"
                event = ActivityEvent(
                    event_type=kind, device_id=self.device_id, timestamp=now,
                    message="Cloud link is online" if state is ConnectivityState.ONLINE else "Cloud link is offline",
                    metadata={"previous_state": previous_state.value, "connectivity": state.value},
                )
                ActivityLog.append_in_transaction(conn, event)
        return state
