from datetime import datetime, timedelta, timezone

from app.edge.state.activity import ActivityEvent, ActivityLog
from app.edge.state.sqlite import EdgeStateDB


def test_activity_order_filter_and_metadata_survive_restart(tmp_path):
    path = tmp_path / "state.db"
    db = EdgeStateDB(path)
    log = ActivityLog(db)
    first = ActivityEvent(
        event_id="event-1", event_type="MEMORY_CREATED", device_id="robot-1", memory_id="memory-1",
        timestamp=datetime(2026, 9, 30, tzinfo=timezone.utc), severity="info", message="created", metadata={"revision": 1},
    )
    second = first.model_copy(update={
        "event_id": "event-2", "event_type": "SYNC_QUEUED", "timestamp": first.timestamp + timedelta(seconds=1),
        "message": "queued", "metadata": {"reason_codes": ["fleet_safe_learned_fact"]},
    })
    log.append(first)
    log.append(second)
    db.close()

    reopened = EdgeStateDB(path)
    log = ActivityLog(reopened)
    events = log.list(10)
    assert [event.event_id for event in events] == ["event-2", "event-1"]
    assert events[0].metadata == {"reason_codes": ["fleet_safe_learned_fact"]}
    assert log.latest_id() == "event-2"
    assert [event.event_id for event in log.list(10, before=second.timestamp)] == ["event-1"]
    reopened.close()
