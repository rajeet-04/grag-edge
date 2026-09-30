import importlib
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "demo" / "seed"
sys.path.insert(0, str(ROOT / "scripts" / "demo"))
EQUIPMENT = {"Pump P-41", "Compressor C-17", "Motor M-08", "Valve V-22"}


def load(name):
    return json.loads((SEED / name).read_text())


@pytest.mark.parametrize("name", ["fleet.json", "robot-local.json", "conflict.json"])
def test_seed_files_are_well_formed_and_stable(name):
    data = load(name)
    memories = data["memories"]
    assert memories
    for key in ("memory_id", "logical_id"):
        ids = [m[key] for m in memories]
        assert len(set(ids)) == len(ids)
        assert all(str(uuid.UUID(i)) == i for i in ids)
    assert all(m["equipment"] in EQUIPMENT and m["equipment"] in m["content"] for m in memories)


def test_fleet_and_local_cover_all_canonical_equipment():
    assert {m["equipment"] for m in load("fleet.json")["memories"]} == EQUIPMENT
    assert {m["equipment"] for m in load("robot-local.json")["memories"]} == EQUIPMENT
    fleet_ids = {m["memory_id"] for m in load("fleet.json")["memories"]}
    local_ids = {m["memory_id"] for m in load("robot-local.json")["memories"]}
    assert not fleet_ids & local_ids


def test_conflict_targets_local_logical_id_with_different_content():
    local = {m["logical_id"]: m for m in load("robot-local.json")["memories"]}
    conflict = load("conflict.json")["memories"][0]
    assert conflict["memory_type"] == "procedure"
    assert conflict["logical_id"] in local and local[conflict["logical_id"]]["content"] != conflict["content"]


class FakeApi:
    def __init__(self):
        self.store, self.posts = {}, 0

    def __call__(self, method, path, body=None):
        if method == "GET":
            mid = path.rsplit("/", 1)[1]
            return (200, self.store[mid]) if mid in self.store else (404, {})
        self.posts += 1
        self.store[body["memory_id"]] = body
        return 201, body


def test_seed_local_is_idempotent_and_verifies_count():
    seed_local = importlib.import_module("seed_local")
    api = FakeApi()
    data = load("robot-local.json")
    assert seed_local.seed(api, data) == {"created": 4, "existing": 0, "total": 4}
    assert seed_local.seed(api, data) == {"created": 0, "existing": 4, "total": 4}
    assert api.posts == 4
    assert all("equipment" not in body for body in api.store.values())


def test_seed_local_fails_when_record_missing_after_write():
    seed_local = importlib.import_module("seed_local")

    class Lossy(FakeApi):
        def __call__(self, method, path, body=None):
            if method == "POST":
                return 201, body
            return super().__call__(method, path, body)

    with pytest.raises(SystemExit):
        seed_local.seed(Lossy(), load("robot-local.json"))


class FakeCloud:
    def __init__(self):
        self.points = {}

    def upsert_point(self, point):
        self.points[point.id] = point

    def retrieve_ids(self, ids):
        return [i for i in ids if i in self.points]


class FakeEmbed:
    async def embed_with_context(self, text, task):
        return [float(len(text) % 7), 1.0, 0.0, 0.5]


async def test_seed_fleet_is_idempotent_and_verifies_count():
    seed_fleet = importlib.import_module("seed_fleet")
    cloud = FakeCloud()
    data = load("fleet.json")
    first = await seed_fleet.seed(cloud, FakeEmbed(), data)
    snapshot = {k: (p.payload["content_hash"], p.payload["sync_state"]) for k, p in cloud.points.items()}
    second = await seed_fleet.seed(cloud, FakeEmbed(), data)
    assert first == second == {"upserted": 4, "total": 4}
    assert len(cloud.points) == 4
    assert snapshot == {k: (p.payload["content_hash"], p.payload["sync_state"]) for k, p in cloud.points.items()}
    payload = next(iter(cloud.points.values())).payload
    assert payload["record_type"] == "memory" and payload["sync_state"] == "SYNCHRONIZED" and payload["device_id"] == "robot-edge-002"
    assert "equipment" not in payload
