"""Small transactional SQLite control-plane database."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class EdgeStateDB:
    """Owns operational metadata, queues, and events; never stores memory text."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sync_outbox (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL UNIQUE,
                    logical_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_attempt_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(logical_id, revision)
                );
                CREATE INDEX IF NOT EXISTS sync_outbox_pending
                    ON sync_outbox(status, created_at);
                CREATE TABLE IF NOT EXISTS sync_attempts (
                    id TEXT PRIMARY KEY,
                    outbox_id TEXT NOT NULL REFERENCES sync_outbox(id),
                    attempt_number INTEGER NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result TEXT NOT NULL DEFAULT 'RUNNING',
                    UNIQUE(outbox_id, attempt_number)
                );
                CREATE TABLE IF NOT EXISTS sync_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    memory_id TEXT,
                    timestamp TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS activity_events_time ON activity_events(timestamp);
                CREATE TABLE IF NOT EXISTS device_state (
                    device_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    logical_id TEXT NOT NULL,
                    local_memory_id TEXT NOT NULL,
                    fleet_memory_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_policy (
                    memory_id TEXT PRIMARY KEY,
                    logical_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    requested_sync_policy TEXT,
                    sync_policy TEXT NOT NULL,
                    sync_state TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    sensitivity TEXT NOT NULL DEFAULT 'fleet_safe',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """
            )
            outbox_columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(sync_outbox)")}
            if "next_attempt_at" not in outbox_columns:
                self._connection.execute("ALTER TABLE sync_outbox ADD COLUMN next_attempt_at TEXT")
            attempt_columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(sync_attempts)")}
            attempt_migrated = "result" not in attempt_columns
            if "started_at" not in attempt_columns:
                self._connection.execute("ALTER TABLE sync_attempts ADD COLUMN started_at TEXT")
            if "finished_at" not in attempt_columns:
                self._connection.execute("ALTER TABLE sync_attempts ADD COLUMN finished_at TEXT")
            if "result" not in attempt_columns:
                self._connection.execute("ALTER TABLE sync_attempts ADD COLUMN result TEXT NOT NULL DEFAULT 'RUNNING'")
            if attempt_migrated:
                self._connection.execute("UPDATE sync_attempts SET started_at=COALESCE(started_at,created_at)")
                self._connection.execute(
                    "UPDATE sync_attempts SET result=CASE "
                    "WHEN error IS NOT NULL THEN 'FAILED' "
                    "WHEN (SELECT status FROM sync_outbox WHERE id=sync_attempts.outbox_id)='UPLOADED' THEN 'SUCCESS' "
                    "WHEN (SELECT status FROM sync_outbox WHERE id=sync_attempts.outbox_id)='CANCELLED' THEN 'CANCELLED' "
                    "ELSE 'INTERRUPTED' END, "
                    "finished_at=CASE WHEN error IS NOT NULL THEN created_at "
                    "WHEN (SELECT status FROM sync_outbox WHERE id=sync_attempts.outbox_id) IN ('UPLOADED','CANCELLED') "
                    "THEN COALESCE((SELECT updated_at FROM sync_outbox WHERE id=sync_attempts.outbox_id),created_at) "
                    "ELSE created_at END"
                )
            policy_columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(memory_policy)")}
            if "sensitivity" not in policy_columns:
                self._connection.execute("ALTER TABLE memory_policy ADD COLUMN sensitivity TEXT NOT NULL DEFAULT 'fleet_safe'")
            if "is_deleted" not in policy_columns:
                self._connection.execute("ALTER TABLE memory_policy ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")
            self._connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS memory_policy_revision ON memory_policy(logical_id, revision)")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialize a transaction on this connection and roll back on any error."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
