from datetime import datetime

from app.edge.state.activity import ActivityLog
from app.edge.state.sqlite import EdgeStateDB
from app.edge.sync.connectivity import ConnectivityMonitor, ConnectivityState
from app.edge.sync.server_client import CloudHealth


class Probe:
    def __init__(self, states):
        self.states = iter(states)

    def health(self):
        return next(self.states)


def test_network_failures_are_offline_auth_failure_is_error_and_transitions_emit_once(tmp_path):
    db = EdgeStateDB(tmp_path / "state.db")
    activity = ActivityLog(db)
    monitor = ConnectivityMonitor(Probe([CloudHealth.OFFLINE, CloudHealth.OFFLINE, CloudHealth.ERROR, CloudHealth.ONLINE, CloudHealth.ONLINE, CloudHealth.OFFLINE]), db, activity, "robot-1")

    assert [monitor.run_once() for _ in range(6)] == [
        ConnectivityState.OFFLINE, ConnectivityState.OFFLINE, ConnectivityState.ERROR,
        ConnectivityState.ONLINE, ConnectivityState.ONLINE, ConnectivityState.OFFLINE,
    ]
    kinds = [event.event_type for event in activity.list(20)]
    assert list(reversed(kinds)) == ["CLOUD_LINK_DOWN", "CLOUD_LINK_UP", "CLOUD_LINK_DOWN"]
    state = monitor.current()
    assert state["connectivity"] == "OFFLINE"
    assert datetime.fromisoformat(state["connectivity_changed_at"])
    db.close()
