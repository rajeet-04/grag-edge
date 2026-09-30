"""Robot A -> Fleet -> Robot B transfer scenario, driven only through public Edge APIs.

Host-side: talks to each robot via `docker exec <container> curl` (API keys stay inside).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEMORY_ID = "10ade000-0000-0000-0011-000000000001"
CONTENT = "Robot lesson: Conveyor C-77 belt slips when humidity exceeds 80 percent; retension before shift."
QUERY = "Conveyor C-77 belt slips humidity"
WAIT = 120


def docker_api(cid):
    def call(method, path, body=None):
        cmd = ["docker", "exec", "-i", cid, "sh", "-c",
               'curl -fsS -m 120 -X "$1" -H "Content-Type: application/json" ${API_KEY:+-H "Authorization: Bearer $API_KEY"} --data-binary @- "http://localhost:8000$2"',
               "_", method, path]
        out = subprocess.run(cmd, input=json.dumps(body or {}), capture_output=True, text=True, check=True).stdout
        return json.loads(out) if out.strip() else {}
    return call


def _find(b, memory_id):
    res = b("POST", "/api/v1/edge/search", {"query": QUERY, "mode": "hybrid", "limit": 10})["results"]
    return next((r for r in res if r["memory_id"] == memory_id), None)


def run_scenario(a, b, go_offline, go_online, sleep=time.sleep, tries=WAIT // 2):
    go_offline()
    a("POST", "/api/v1/edge/memories", {"memory_id": MEMORY_ID, "memory_type": "observation", "content": CONTENT,
        "importance": "high", "sync_policy": "auto", "sensitivity": "fleet_safe", "device_id": "ROBOT-01", "tags": ["conveyor", "C-77"]})
    assert _find(b, MEMORY_ID) is None, "Robot B saw A's memory before sync"
    go_online()
    hit = None
    for _ in range(tries):
        a("POST", "/api/v1/edge/sync/run")
        if a("GET", f"/api/v1/edge/memories/{MEMORY_ID}").get("sync_state") == "SYNCHRONIZED":
            b("POST", "/api/v1/edge/sync/run")
            hit = _find(b, MEMORY_ID)
            if hit:
                break
        sleep(2)
    assert hit, "Robot B never received the synchronized memory"
    assert hit["origin"] == "FLEET", f"expected FLEET origin, got {hit['origin']}"
    assert hit["device_id"] == "ROBOT-01", f"expected ROBOT-01, got {hit['device_id']}"
    return {"memory_id": hit["memory_id"], "origin": hit["origin"], "device_id": hit["device_id"]}


def _cid(service):
    ids = subprocess.run(["bash", "-c", f'source scripts/demo/lib.sh; compose --profile fleet-demo ps -q {service}'],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert len(ids) == 1, f"expected one {service} container, found {len(ids)}"
    return ids[0]


def main():
    cid_a, cid_b = _cid("fastapi"), _cid("robot-b-api")
    sh = lambda script: subprocess.run(["bash", str(ROOT / "scripts/demo" / script)], cwd=ROOT, check=True)
    result = run_scenario(docker_api(cid_a), docker_api(cid_b), lambda: sh("offline.sh"), lambda: sh("online.sh"))
    print("FLEET TRANSFER PASSED:", json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        sys.exit(f"demo: {exc}")
