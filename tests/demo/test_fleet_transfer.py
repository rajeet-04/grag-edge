import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("fleet_transfer", ROOT / "scripts/demo/fleet_transfer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeFleet:
    """A/B fake APIs sharing only a 'fleet' set, mimicking upload + refresh."""

    def __init__(self, leak=False):
        self.a_mem, self.fleet, self.b_view, self.events = {}, {}, {}, []
        self.leak = leak

    def a(self, method, path, body=None):
        if method == "POST" and path.endswith("/memories"):
            self.a_mem[body["memory_id"]] = body
            if self.leak:
                self.b_view[body["memory_id"]] = {**body, "origin": "LOCAL"}
            return {}
        if method == "GET" and "/memories/" in path:
            return {"sync_state": "SYNCHRONIZED" if self.fleet else "PENDING"}
        if path.endswith("/sync/run"):
            self.fleet.update(self.a_mem)
        return {}

    def b(self, method, path, body=None):
        if path.endswith("/sync/run"):
            self.b_view = {k: {**v, "origin": "FLEET"} for k, v in self.fleet.items()}
            return {}
        if path.endswith("/search"):
            return {"results": [{"memory_id": k, "origin": v["origin"], "device_id": v["device_id"]} for k, v in self.b_view.items()]}
        return {}

    def offline(self):
        self.events.append("offline")

    def online(self):
        self.events.append("online")


def test_transfer_reaches_b_as_fleet_from_robot_01():
    ft, f = load(), FakeFleet()
    result = ft.run_scenario(f.a, f.b, f.offline, f.online, sleep=lambda s: None)
    assert result == {"memory_id": ft.MEMORY_ID, "origin": "FLEET", "device_id": "ROBOT-01"}
    assert f.events == ["offline", "online"]


def test_scenario_fails_if_b_sees_unsynced_memory():
    ft, f = load(), FakeFleet(leak=True)
    with pytest.raises(AssertionError, match="before sync"):
        ft.run_scenario(f.a, f.b, f.offline, f.online, sleep=lambda s: None)


def test_make_target_exists():
    assert subprocess.run(["make", "-n", "demo-robot-b"], cwd=ROOT, capture_output=True).returncode == 0
