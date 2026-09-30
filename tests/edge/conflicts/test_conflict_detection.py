from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import sqlite3

from app.edge.conflicts import ConflictRecord, ConflictService
from app.edge.memory.models import MemoryRecord, MemoryType, SyncState
from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB


def memory(
    *,
    memory_id: str,
    content: str,
    memory_type: MemoryType = MemoryType.PROCEDURE,
    logical_id: str = "pump-procedure",
    revision: int = 2,
    parent_revision: int | None = 1,
    device_id: str = "robot-local",
    source_type: str | None = "operator",
    source_id: str | None = "shift-17",
    sync_state: SyncState = SyncState.LOCAL_DIRTY,
) -> MemoryRecord:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    return MemoryRecord(
        memory_id=memory_id,
        logical_id=logical_id,
        device_id=device_id,
        memory_type=memory_type,
        content=content,
        created_at=now,
        updated_at=now,
        revision=revision,
        parent_revision=parent_revision,
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
        source_type=source_type,
        source_id=source_id,
        sync_state=sync_state,
    )


def service(tmp_path):
    db = EdgeStateDB(tmp_path / "edge-state.sqlite")
    return db, ConflictService(db, ActivityLog(db))


def test_procedure_divergence_persists_shared_base_identity_and_provenance(tmp_path):
    db, conflicts = service(tmp_path)
    local = memory(memory_id="local-v2", content="Inspect the seal first")
    fleet = memory(
        memory_id="fleet-v2", content="Check the bearing first", device_id="robot-fleet",
        source_type="maintenance-log", source_id="log-42", sync_state=SyncState.SYNCHRONIZED,
    )

    result = conflicts.detect(local, fleet)

    assert isinstance(result, ConflictRecord)
    assert result.conflict_id.startswith("conflict_")
    assert result.logical_id == local.logical_id
    assert result.base_revision == 1
    assert result.memory_type is MemoryType.PROCEDURE
    assert (result.local_memory_id, result.fleet_memory_id) == ("local-v2", "fleet-v2")
    assert (result.local_revision, result.fleet_revision) == (2, 2)
    assert (result.local_source_type, result.local_source_id) == ("operator", "shift-17")
    assert (result.fleet_source_type, result.fleet_source_id) == ("maintenance-log", "log-42")
    assert result.local_sync_state is SyncState.LOCAL_DIRTY
    assert result.fleet_sync_state is SyncState.SYNCHRONIZED
    assert result.status == "OPEN"
    assert conflicts.get(result.conflict_id) == result
    assert conflicts.list_open() == [result]
    # SQLite contains a metadata snapshot but never stores either memory's text.
    with db._lock:
        row = db._connection.execute("SELECT * FROM conflicts").fetchone()
    assert row["local_memory_id"] == "local-v2"
    assert row["fleet_memory_id"] == "fleet-v2"
    assert ConflictRecord.model_validate_json(row["metadata_json"]) == result
    assert "Inspect the seal first" not in str(tuple(row))
    assert "Check the bearing first" not in str(tuple(row))
    db.close()


def test_learned_fact_divergence_is_conflict_sensitive(tmp_path):
    db, conflicts = service(tmp_path)

    result = conflicts.detect(
        memory(memory_id="local-fact", content="The valve seals at 40 kPa", memory_type=MemoryType.LEARNED_FACT),
        memory(memory_id="fleet-fact", content="The valve seals at 45 kPa", memory_type=MemoryType.LEARNED_FACT),
    )

    assert result is not None
    assert result.memory_type is MemoryType.LEARNED_FACT
    db.close()


def test_observations_and_incidents_remain_append_only(tmp_path):
    db, conflicts = service(tmp_path)
    for kind in (MemoryType.OBSERVATION, MemoryType.INCIDENT):
        assert conflicts.detect(
            memory(memory_id=f"local-{kind.value}", content="event one", memory_type=kind),
            memory(memory_id=f"fleet-{kind.value}", content="event two", memory_type=kind),
        ) is None
    db.close()


def test_identical_revision_content_is_not_a_conflict(tmp_path):
    db, conflicts = service(tmp_path)

    assert conflicts.detect(
        memory(memory_id="local-v2", content="same procedure"),
        memory(memory_id="fleet-v2", content="same procedure", sync_state=SyncState.SYNCHRONIZED),
    ) is None
    db.close()


def test_different_logical_ids_or_different_bases_are_not_conflicts(tmp_path):
    db, conflicts = service(tmp_path)
    local = memory(memory_id="local-v2", content="local procedure")

    assert conflicts.detect(local, memory(memory_id="fleet-other", logical_id="another", content="fleet procedure")) is None
    assert conflicts.detect(local, memory(memory_id="fleet-unrelated", parent_revision=0, content="fleet procedure")) is None
    assert conflicts.detect(local, memory(memory_id="fleet-root", parent_revision=None, revision=1, content="fleet procedure")) is None
    db.close()


def test_same_divergence_emits_one_event_and_remains_durable_after_restart(tmp_path):
    path = tmp_path / "edge-state.sqlite"
    db = EdgeStateDB(path)
    conflicts = ConflictService(db, ActivityLog(db))
    local = memory(memory_id="local-v2", content="local edit")
    fleet = memory(memory_id="fleet-v2", content="fleet edit")

    first = conflicts.detect(local, fleet)
    second = conflicts.detect(local, fleet)

    assert first == second
    assert [event.event_type for event in ActivityLog(db).list(10)] == ["CONFLICT_DETECTED"]
    db.close()
    reopened = EdgeStateDB(path)
    reopened_conflicts = ConflictService(reopened, ActivityLog(reopened))
    assert reopened_conflicts.get(first.conflict_id) == first
    assert reopened_conflicts.list_open() == [first]
    assert [event.event_type for event in ActivityLog(reopened).list(10)] == ["CONFLICT_DETECTED"]
    reopened.close()


def test_concurrent_duplicate_detection_inserts_one_conflict_and_event(tmp_path):
    db, conflicts = service(tmp_path)
    local = memory(memory_id="local-v2", content="local edit")
    fleet = memory(memory_id="fleet-v2", content="fleet edit")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: conflicts.detect(local, fleet), range(24)))

    assert len({result.conflict_id for result in results}) == 1
    assert len(conflicts.list_open()) == 1
    assert [event.event_type for event in ActivityLog(db).list(10)] == ["CONFLICT_DETECTED"]
    db.close()


def test_existing_conflicts_table_migration_preserves_reference_columns(tmp_path):
    path = tmp_path / "legacy-state.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE conflicts (conflict_id TEXT PRIMARY KEY, logical_id TEXT NOT NULL, "
        "local_memory_id TEXT NOT NULL, fleet_memory_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO conflicts VALUES('legacy-conflict','logical-1','local-uuid','fleet-uuid','OPEN','2026-09-30T12:00:00+00:00')"
    )
    connection.commit()
    connection.close()

    db = EdgeStateDB(path)

    with db._lock:
        columns = {row["name"] for row in db._connection.execute("PRAGMA table_info(conflicts)")}
        row = db._connection.execute("SELECT * FROM conflicts WHERE conflict_id='legacy-conflict'").fetchone()
    assert "metadata_json" in columns
    assert row["local_memory_id"] == "local-uuid"
    assert row["fleet_memory_id"] == "fleet-uuid"
    assert row["metadata_json"] == "{}"
    db.close()
